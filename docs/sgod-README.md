# Cxodex 选股神器（SGOD）使用手册

SGOD（Stock Screener + Guru Outlook + Deep-dive 的内部代号）是挂在本仓库既有个股深度分析流水线（`main.py`）之上的**每日全市场选股编排器**：从全市场快照初筛候选，复用上游深度分析，再叠加财务解读、量化买点、行业情报与仓位建议，最终产出一份自包含 HTML 日报，并可选推送到企业微信。

代码位置：`screener/`（初筛）、`imds_finance/`（财务分析）、`industry_intel/`（行业情报）、`portfolio_advisor/`（策略建议）、`sgod/`（LLM 客户端、企业微信推送、HTML 报告），总入口 `run_daily.py`。

---

## 1. 功能一览

| 能力 | 模块 | 做什么 | 关键降级行为 |
|---|---|---|---|
| **自动荐股** | `screener/` | 全市场快照（akshare）→ 硬性条件过滤（价格/成交额/PE/上市天数/ST 黑名单）→ 财务/技术/资金三维打分 → 剔除 14 天内已荐个股 → 取 Top N | 单维数据缺失记中性分 50，不剔除；快照接口失败会抛 `SnapshotError`，整场次中断（见第 6 节） |
| **IMDS 财务分析与展望** | `imds_finance/` | 拉取近 8 季度财报（A股 akshare 财务摘要 / 美股 yfinance 三大报表），算出同行对比卡、管理层视角卡、风险扫描卡与财务健康分，再由 GLM 生成「管理层分析和关注」「财务展望」两段文字 | 科目映射不到记 `None`，不编造数字；`GLM_API_KEY` 未配置或调用失败时 `analysis_text`/`outlook_text` 为 `None`，HTML 显示「AI 分析暂缺」 |
| **量化买点** | `screener/buypoint.py` | 基于近 60 日 K 线算支撑（近20日低点与MA20较高者）/压力（近60日高点），给出买入区间 `[支撑, min(MA5, 现价×1.01)]`，乖离率超 8% 提示「观望」 | K 线不足 20 根或缺现价 → 返回 `None`，不猜测买点 |
| **投资策略建议** | `portfolio_advisor/` | 按资金规模、风险偏好（保守/均衡/激进）、单票/单行业仓位上限选出候选组合，按 60% 首建 + 40% 加仓两批建仓，GLM 生成组合逻辑/风险/止盈止损说明 | 无买点或买点为「观望」的候选不参与分配；资金 ≤0 时返回空组合；无持仓或 GLM 失败时 `advisor_text` 为 `None` |
| **行业情报** | `industry_intel/` | 按候选股所属行业分组，Tavily 搜索近 7 天中/英文行业新闻，交给 GLM 判断利好/利空/中性、影响窗口、对候选股的一句话影响 | `TAVILY_API_KEY` 未配置 → 新闻列表为 `[]`（仍会让 GLM 按宏观常识判断并标注不确定性）；GLM 未配置或失败 → `assessment` 为 `None` |

---

## 2. CLI 用法

### 2.1 `run_daily.py`（推荐入口，完整场次）

```bash
python run_daily.py --market <a|us> [--limit N] [--dry-run] [--no-deep] [--no-notify]
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `--market` | `{a,us}` | 必填 | `a`=A股场次，`us`=美股场次 |
| `--limit` | int | `None` | 候选数上限（调试用，覆盖 `config/sgod.yaml` 里的 `screener.top_n`） |
| `--dry-run` | flag | 关 | 不推送、不写入推荐历史（`RecommendHistory`），只跑一遍产出 HTML 日报；本机冒烟必开 |
| `--no-deep` | flag | 关 | 跳过对 `main.py` 深度分析子进程的调用（该子进程默认超时 1800s，`--stocks <codes> --no-notify --force-run`）；本机冒烟建议开启以缩短耗时 |
| `--no-notify` | flag | 关 | 只关闭企业微信推送，但仍会写入推荐历史（与 `--dry-run` 的差异：`--dry-run` 两者都不写） |

执行完成后打印一行摘要：

```
完成：Top<N>，日报 data/sgod/reports/<日期>-<market>.html，推送 成功/未推送
```

若过程中任意环节抛出未捕获异常，`run_daily.py` 会尝试通过企业微信告警（`send_wecom`，未配置 webhook 则静默失败），随后以 `SystemExit(1)` 退出——**这是有意设计**：`SystemExit` 不会打印原始异常堆栈，因此终端看起来"无输出直接退出码 1"是预期现象，不是脚本本身崩溃；要看到具体异常，请改用下面的 `screener.run` 直接调用。

### 2.2 `python -m screener.run`（仅跑初筛，用于定位问题）

```bash
python -m screener.run --market <a|us> [--dry-run] [--top N]
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `--market` | `{a,us}` | 必填 | 同上 |
| `--dry-run` | flag | 关 | 只打印 JSON（`code/name/score/tags/buy`），不写历史 |
| `--top` | int | `None` | 候选数上限 |

此命令**不捕获异常**，网络/快照失败会打印完整 Python 堆栈，是本机排障与本手册"已知限制"一节记录冒烟结果时使用的方式。

### 2.3 安装依赖

```bash
pip install -r requirements.txt pyyaml
```

`pyyaml` 用于加载 `config/sgod.yaml`；`akshare`/`yfinance`/`requests` 等已在 `requirements.txt` 中。

---

## 3. 环境变量表

以下变量均为可选，缺失时对应能力按第 1 节的"降级行为"运行，不会导致整个流程崩溃（网络类异常除外，见第 6 节）。

| 变量 | 默认值 | 用途 | 缺失/未配置时的行为 |
|---|---|---|---|
| `GLM_API_KEY` | 无 | 智谱 GLM（OpenAI 兼容协议）调用密钥，驱动 IMDS 财务分析/展望、行业情报判断、策略建议文案 | `sgod/llm.py::chat()` 直接返回 `None`，所有依赖 LLM 的文本字段变为 `None`/暂缺 |
| `GLM_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4` | GLM API base URL | 使用默认官方地址 |
| `GLM_MODEL` | `glm-5.2` | 调用的模型名 | 使用默认模型 |
| `SGOD_LLM_RETRY_BASE` | `2.0` | LLM 请求遇 429/500/502/503/504 时的指数退避基数（等待 = base × 2^i，共重试 3 次） | 使用默认 2.0s 基数 |
| `SGOD_WECOM_WEBHOOK` | 无 | 企业微信群机器人 Webhook 地址，`sgod/wecom.py::send_wecom()` 用它推送日报 Markdown | `send_wecom()` 直接返回 `False`，即"未推送"，不报错 |
| `TAVILY_API_KEY` | 无 | Tavily 搜索 API，`industry_intel/run.py` 用它抓行业近 7 天新闻标题 | `_search()` 返回 `[]`，情报仍会生成但新闻为空，GLM 按"无新闻，仅按常识性宏观背景判断"提示词处理 |
| `SGOD_CAPITAL` | `config/sgod.yaml` 的 `advisor.capital_base`（默认 100000） | 策略建议模块的可用本金 | 使用配置文件默认值 |
| `SGOD_RISK_PROFILE` | `balanced` | 风险偏好档位，取值 `conservative`/`balanced`/`aggressive`，对应 `config/sgod.yaml` 的 `advisor.risk_profiles` 三档参数 | 使用 `balanced`（均衡） |
| `SGOD_WEB_URL` | `https://stock.cxodex.com` | 拼接进企业微信推送 Markdown 里的"完整报告"链接前缀（实际链接 = `SGOD_WEB_URL/daily/<html文件名>`） | 使用默认域名，若该域名未部署对应静态服务，链接会失效但不影响推送本身 |

> 未在此表中，但同属 sgod 依赖链路的说明：GLM/Tavily/WeCom 三者互不影响——比如只配置 `GLM_API_KEY` 而不配置 `TAVILY_API_KEY`，行业情报仍会跑（新闻为空），财务分析/策略文案正常生成。

---

## 4. `config/sgod.yaml` 参数说明

```yaml
screener:
  top_n: 20                     # 最终产出候选数上限（可被 --limit/--top 覆盖）
  dedup_days: 14                 # 去重窗口：N 天内已推荐过的代码不再出现
  subnew_max_days: 250            # 上市 ≤250 交易日 → 打"次新"标签（仅打标，不剔除）
  a:                              # A股专属硬性条件
    min_listing_days: 20          # 上市天数下限
    min_turnover_amt: 100000000   # 最小成交额（元），1亿
    min_price: 2.0                # 最低股价
    exclude_loss: true            # PE<0 剔除；PE 缺失不剔除
    name_blacklist: ["ST", "*ST", "退"]   # 名称包含以下任一子串即剔除
  us:                              # 美股专属硬性条件（结构同上）
    min_listing_days: 20
    min_turnover_amt: 50000000    # 最小成交额（美元），5000万
    min_price: 2.0
    exclude_loss: true
    name_blacklist: []
scoring:
  weights: {finance: 0.4, technical: 0.3, flow: 0.3}   # 三维打分加权系数，需自行保证总和语义合理（当前刚好=1.0）
advisor:
  capital_base: 100000            # 默认本金；可被 SGOD_CAPITAL 覆盖
  risk_profiles:
    conservative: {max_pos: 0.10, max_industry: 0.30, min_cash: 0.50, n_picks: 3}
    balanced:     {max_pos: 0.15, max_industry: 0.30, min_cash: 0.30, n_picks: 4}
    aggressive:   {max_pos: 0.25, max_industry: 0.30, min_cash: 0.10, n_picks: 6}
```

各风险档位字段含义：

- `max_pos`：单只候选最多占用的资金比例（相对 `capital_base`/`SGOD_CAPITAL`）
- `max_industry`：单个行业最多占用的资金比例
- `min_cash`：策略建议至少保留的现金比例（即最多投入 `1 - min_cash`）
- `n_picks`：最多选入几只候选进入组合

改参数不用改代码，直接编辑 `config/sgod.yaml` 即可（由 `screener/filters.py::load_sgod_config()` 在每次运行时读取，无缓存）。

---

## 5. 数据流（文字版）

```
akshare 全市场快照 (stock_zh_a_spot_em / stock_us_spot_em，_retry 3次指数退避2/4/8s)
        │
        ▼
硬性条件过滤 hard_filter（黑名单/价格/成交额/PE/上市天数）
        │
        ▼
三维打分 score_row（finance/technical/flow，缺数据记中性50，加权求和）
        │
        ▼
取前50名短名单 → A股二次精查（逐只补上市天数，重新过滤+打分）
        │
        ▼
RecommendHistory 去重（剔除 dedup_days 天内已推荐代码）→ 取 Top N（--limit/--top 可覆盖）
        │
        ▼
量化买点 buy_zone（近60日K线 → 支撑/压力/买入区间/仓位提示/触发条件）
        │
        ├──[--no-deep 未设置时]── main.py 深度分析子进程
        │        （--stocks <codes> --no-notify --force-run，超时1800s，失败仅告警不中断日报）
        │
        ▼
逐只候选：fetch_industry + fetch_series（财报：A股akshare摘要/美股yfinance三表）
        │        → IMDS 三卡（同行对比/管理层视角/风险扫描）+ health_score
        │        → GLM 生成「管理层分析和关注」「财务展望」（GLM_API_KEY 缺失/失败 → None）
        ▼
行业情报 gather_intel（按行业分组 → Tavily近7天新闻[缺key→[]] → GLM 利好/利空/中性判断[缺key/失败→None]）
        │
        ▼
策略建议 allocate（按资金/风险偏好/仓位上限选组合，60%首建+40%加仓）
        │        → GLM 生成组合逻辑/风险/止盈止损说明（无持仓或GLM失败 → None）
        ▼
write_html_report → 自包含 HTML 日报（Top表格 + 策略表 + 行业情报 + 个股IMDS财务卡 + 免责声明）
        │        写入 data/sgod/reports/<日期>-<market>.html，并刷新 index.html（保留最近60份）
        ▼
[--dry-run 未设置且未 --no-notify] build_daily_markdown（4000字节截断，三级降级：全量→砍情报→砍策略）
        │        → send_wecom（SGOD_WECOM_WEBHOOK 未配置 → 返回 False，即"未推送"）
        ▼
[--dry-run 未设置] RecommendHistory.record 写入推荐历史（--no-notify 时仍会写，--dry-run 时不写）
```

---

## 6. 已知限制

1. **美股无同行中位数**：`imds_finance/fetch.py::fetch_peer_median()` 在 `market != "a"` 时直接返回 `None`，不臆造同行数据；美股财务健康分不会有"同行加减分"环节，仅基于自身财报打分。
2. **东财快照限流与超时降级语义**：
   - 全市场快照 `fetch_snapshot()` 用 `_retry()` 包裹 akshare 的 `stock_zh_a_spot_em`/`stock_us_spot_em`，失败时按 2s/4s/8s 指数退避重试 3 次；仍失败会抛出 `screener.snapshot.SnapshotError`，**中断当次场次**（不是优雅降级，而是整场失败）。
   - `run_daily.py` 顶层 `try/except` 会捕获该异常并尝试企业微信告警（未配置 webhook 则静默失败），随后 `raise SystemExit(1)`——**`SystemExit` 不打印原始异常堆栈**，终端表现为"无任何输出、退出码 1"，这是设计使然，不代表脚本本身有 bug。要看到具体的异常信息，请改用 `python -m screener.run --market <a|us> --dry-run --top N` 直接调用（该命令不捕获异常，会打印完整堆栈）。
   - `fetch_listing_days_a()` 对短名单逐只补上市天数时加了 0.3s 限流保护，单只失败记 `None`，不阻塞其余候选。
   - `fetch_klines`/`fetch_series`/`fetch_industry`/`fetch_peer_median` 均对单只候选的异常做了静默捕获（返回 `[]`/`None`），不会因单只股票的数据源问题拖垮整批。
3. **LLM 失败降级不臆造**：`sgod/llm.py::chat()` 无 `GLM_API_KEY` 直接返回 `None`；HTTP 429/500/502/503/504 会重试 3 次（指数退避，基数 `SGOD_LLM_RETRY_BASE`）后仍失败返回 `None`；其他 HTTP 错误判定为 `fatal`，立即返回 `None`；响应结构异常（缺字段/类型不对）同样返回 `None`。所有依赖 GLM 的文本（财务分析/展望、行业情报判断、策略建议说明）在失败时均为 `None`，HTML/推送侧会展示"暂缺"而不是编造内容。
4. **非交易日快照自然为空/或被过滤**：akshare 全市场接口返回的是最近一个交易日快照；若当天尚无成交数据，`turnover_amt` 等字段可能缺失，从而被 `hard_filter` 的成交额门槛剔除，导致该场次候选数偏少甚至为 0——这是预期行为，不是 bug。
5. **本机冒烟网络状况记录（如实记录，2026-07-29）**：本机对东方财富行情接口（`82.push2.eastmoney.com` / `72.push2.eastmoney.com`）访问不稳定，A股与美股两个场次的 `python -m screener.run` 冒烟均以 `screener.snapshot.SnapshotError: HTTPSConnectionPool(host=..., port=443): Read timed out. (read timeout=15)` 失败，重试一次后仍失败（与 Task 6 阶段记录的"本机东财接口超时"现象一致）。因快照阶段即失败，本次未能产出 `data/sgod/reports/` 下的 HTML 日报，故未能现场核验报告页面渲染；HTML 生成逻辑本身（Top 表格 + 财务卡 + 免责声明）已在 `sgod/html_report.py` 源码走查中确认覆盖第 1 节列出的全部字段。生产/CI 环境若网络可达 eastmoney，预期能正常产出报告；若长期不可达，可考虑腾讯行情源等替代快照数据源作为后续增强项（不在本任务范围内）。

---

## 7. 免责声明

本报告由 AI 生成，仅供研究参考，不构成投资建议，据此操作风险自负。
