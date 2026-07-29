# 双市场选股神器实施计划（A股+美股）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 fork 的 daily_stock_analysis 上增量挂载 5 个新能力：全市场自动荐股（新股+老股）、IMDS 财务分析与展望、量化买点提示、投资策略建议、行业情报——原有功能不动，最终部署到 HK 服务器 stock.cxodex.com 并每日企业微信推送。

**Architecture:** 新增 4 个顶层独立包（`screener/`、`imds_finance/`、`industry_intel/`、`portfolio_advisor/`）+ 共用工具包 `sgod/`（LLM 客户端、企业微信推送）+ 编排器 `run_daily.py`。编排器：初筛 → 以 `python main.py --stocks <top20> --no-notify` 子进程复用原深度分析流水线 → 财务/情报/策略三模块 → 组合成日报（企业微信 markdown + 静态 HTML）。上游文件零修改（只加文件），保留 `git merge upstream/main`。

**Tech Stack:** Python 3.10+、AkShare（A股+美股快照、A股财报）、yfinance（美股财报）、GLM5.2（智谱 OpenAI 兼容 API）、企业微信 webhook、pytest、PM2 + nginx + certbot（HK 服务器）。

## Global Constraints

- 上游已有文件一律不修改（Route A）；新代码全部在新文件里
- 所有纯计算函数：缺失/非法输入返回 `None`（或跳过该项），绝不抛错、绝不臆造数字（对齐 cxodex-finance-app calc.js 风格）
- 网络调用与纯计算分离：fetch 层薄、可 mock；计算层零网络依赖、全部单测
- AkShare/yfinance 列名用同义词映射表匹配（上游接口列名常变），映射不到 → None
- 每份对外输出固定尾注：`本报告由 AI 生成，仅供研究参考，不构成投资建议，据此操作风险自负`
- LLM 走 OpenAI 兼容接口，环境变量：`GLM_API_KEY`、`GLM_BASE_URL`（默认 `https://open.bigmodel.cn/api/paas/v4`）、`GLM_MODEL`（默认 `glm-5.2`）
- 企业微信推送环境变量：`SGOD_WECOM_WEBHOOK`（与上游 `WECHAT_WEBHOOK_URL` 独立，互不影响）
- 测试命令统一 `python -m pytest tests_sgod/ -v`（新测试独立目录，不与上游 600+ 测试混跑）
- 提交信息前缀 `feat(sgod):` / `test(sgod):` / `docs(sgod):`（sgod = Stock God 选股神器）

## 文件结构总览

```
screener/                    # 第1级全市场初筛
  __init__.py
  norm.py                    # 快照行归一化（同义词映射→标准字段 dict）
  filters.py                 # 硬条件过滤（纯函数）
  scoring.py                 # 三维量化打分（纯函数）
  buypoint.py                # 量化买点：支撑/压力/买入区间（纯函数）
  history.py                 # 推荐历史 SQLite（14天新面孔去重）
  snapshot.py                # AkShare A股/美股快照拉取（薄网络层）
  run.py                     # 初筛编排：fetch→filter→score→dedup→TopN
imds_finance/                # IMDS 财务分析与展望
  __init__.py
  ratios.py                  # 同行对比/管理层/风险三卡比率计算（纯函数）
  scoring.py                 # 财务健康评分 0-100（纯函数）
  fetch.py                   # A股(AkShare)/美股(yfinance) 财报适配器
  report.py                  # 三卡 JSON + GLM「管理层分析和关注」「财务展望」
industry_intel/              # 行业经济政治情报
  __init__.py
  run.py                     # 行业聚合→搜索→GLM 影响预测
portfolio_advisor/           # 投资策略建议
  __init__.py
  allocate.py                # 仓位分配纯计算（风险偏好/行业上限/一手取整）
  report.py                  # GLM 组合逻辑说明
sgod/                        # 共用工具
  __init__.py
  llm.py                     # GLM OpenAI 兼容客户端（重试/退避）
  wecom.py                   # 企业微信 markdown 推送
  html_report.py             # 静态 HTML 日报生成
run_daily.py                 # 总编排器 CLI
config/sgod.yaml             # 过滤阈值/打分权重/仓位参数（可调不改代码）
tests_sgod/                  # 全部新增测试
deploy/sgod/                 # 部署物：nginx conf、cron、.env 模板、部署手册
```

---

### Task 1: 快照行归一化 `screener/norm.py`

**Files:**
- Create: `screener/__init__.py`（空文件）
- Create: `screener/norm.py`
- Test: `tests_sgod/test_norm.py`
- Create: `tests_sgod/__init__.py`（空文件）

**Interfaces:**
- Produces: `normalize_row(row: dict, market: str) -> dict` — 输入 AkShare 快照一行（中文列名 dict），输出标准字段 dict：`{code, name, market, price, pct_chg, turnover_amt, volume_ratio, turnover_rate, pe, pb, total_mv, circ_mv, pct_60d, listing_days}`；缺失字段为 `None`。`code` A股为 6 位数字串，美股为大写 ticker（东财 `105.AAPL` → `AAPL`）。
- Produces: `to_float(v) -> float | None` — 千分位/全角/`"-"`/空串安全转换。

- [ ] **Step 1: 写失败测试**

```python
# tests_sgod/test_norm.py
from screener.norm import normalize_row, to_float

def test_to_float_handles_junk():
    assert to_float("1,234.5") == 1234.5
    assert to_float("-") is None
    assert to_float(None) is None
    assert to_float("") is None
    assert to_float(3.14) == 3.14

def test_normalize_a_share_row():
    row = {"代码": "600519", "名称": "贵州茅台", "最新价": "1450.0", "涨跌幅": "1.2",
           "成交额": "5600000000", "量比": "1.1", "换手率": "0.3",
           "市盈率-动态": "22.5", "市净率": "7.8", "总市值": "1820000000000",
           "流通市值": "1820000000000", "60日涨跌幅": "5.5"}
    r = normalize_row(row, "a")
    assert r["code"] == "600519" and r["market"] == "a"
    assert r["pe"] == 22.5 and r["turnover_amt"] == 5.6e9
    assert r["listing_days"] is None  # 快照没有上市天数，后续补

def test_normalize_us_row_strips_prefix():
    row = {"代码": "105.AAPL", "名称": "苹果", "最新价": "228.1", "涨跌幅": "-0.4",
           "成交额": "8100000000", "市盈率": "34.2"}
    r = normalize_row(row, "us")
    assert r["code"] == "AAPL" and r["pe"] == 34.2
    assert r["pb"] is None  # 美股快照无市净率 → None 不臆造
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests_sgod/test_norm.py -v`
Expected: FAIL（ModuleNotFoundError: screener）

- [ ] **Step 3: 最小实现**

```python
# screener/norm.py
# 快照行归一化：中文列名同义词 → 标准字段。缺失返回 None，不臆造。
from __future__ import annotations

SYNONYMS = {
    "code": ["代码", "股票代码"],
    "name": ["名称", "股票名称"],
    "price": ["最新价", "现价"],
    "pct_chg": ["涨跌幅"],
    "turnover_amt": ["成交额"],
    "volume_ratio": ["量比"],
    "turnover_rate": ["换手率"],
    "pe": ["市盈率-动态", "市盈率", "市盈率TTM"],
    "pb": ["市净率"],
    "total_mv": ["总市值"],
    "circ_mv": ["流通市值"],
    "pct_60d": ["60日涨跌幅"],
}

def to_float(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        import math
        return float(v) if not (isinstance(v, float) and math.isnan(v)) else None
    s = str(v).replace(",", "").replace("，", "").strip()
    if s in ("-", "--", "None", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None

def _pick(row: dict, key: str):
    for syn in SYNONYMS[key]:
        if syn in row:
            return row[syn]
    return None

def normalize_row(row: dict, market: str) -> dict:
    code = str(_pick(row, "code") or "").strip()
    if market == "us" and "." in code:
        code = code.split(".", 1)[1].upper()
    out = {"code": code, "name": _pick(row, "name"), "market": market,
           "listing_days": None}
    for k in ("price", "pct_chg", "turnover_amt", "volume_ratio",
              "turnover_rate", "pe", "pb", "total_mv", "circ_mv", "pct_60d"):
        out[k] = to_float(_pick(row, k))
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests_sgod/test_norm.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add screener/ tests_sgod/
git commit -m "feat(sgod): 快照行归一化——同义词映射+null安全转换"
```

---

### Task 2: 硬条件过滤 `screener/filters.py`

**Files:**
- Create: `screener/filters.py`
- Create: `config/sgod.yaml`
- Test: `tests_sgod/test_filters.py`

**Interfaces:**
- Consumes: Task 1 的标准字段 dict
- Produces: `hard_filter(rows: list[dict], market: str, cfg: dict) -> list[dict]`；`load_sgod_config(path=None) -> dict`（读 `config/sgod.yaml`）。通过过滤的行会加 `tags: list[str]` 字段（如 `["次新"]`）。

- [ ] **Step 1: 写失败测试**

```python
# tests_sgod/test_filters.py
from screener.filters import hard_filter, load_sgod_config

CFG = load_sgod_config()

def _row(**kw):
    base = {"code": "600000", "name": "浦发银行", "market": "a", "price": 10.0,
            "pct_chg": 1.0, "turnover_amt": 5e8, "volume_ratio": 1.0,
            "turnover_rate": 2.0, "pe": 8.0, "pb": 0.6, "total_mv": 3e10,
            "circ_mv": 3e10, "pct_60d": 3.0, "listing_days": 1000}
    base.update(kw)
    return base

def test_filters_out_st_and_cheap_and_illiquid():
    rows = [_row(), _row(name="ST某某"), _row(price=1.5), _row(turnover_amt=5e7),
            _row(pe=-3.0), _row(listing_days=10)]
    kept = hard_filter(rows, "a", CFG)
    assert len(kept) == 1 and kept[0]["name"] == "浦发银行"

def test_subnew_gets_tag_not_dropped():
    kept = hard_filter([_row(listing_days=100)], "a", CFG)
    assert kept and "次新" in kept[0]["tags"]

def test_us_filters_price_and_liquidity():
    rows = [_row(market="us", code="AAPL", price=228.0, turnover_amt=8e9, pe=30.0),
            _row(market="us", code="PENNY", price=1.2),
            _row(market="us", code="THIN", turnover_amt=1e7)]
    kept = hard_filter(rows, "us", CFG)
    assert [r["code"] for r in kept] == ["AAPL"]

def test_missing_fields_do_not_crash():
    kept = hard_filter([_row(pe=None, pct_60d=None)], "a", CFG)
    assert kept  # PE 缺失不按亏损处理，放行交给打分层
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests_sgod/test_filters.py -v`
Expected: FAIL

- [ ] **Step 3: 写 `config/sgod.yaml` 与实现**

```yaml
# config/sgod.yaml — 选股神器可调参数（改这里不用改代码）
screener:
  top_n: 20
  dedup_days: 14
  subnew_max_days: 250          # 上市≤250交易日 → 打"次新"标签
  a:
    min_listing_days: 20
    min_turnover_amt: 100000000   # 1亿元
    min_price: 2.0
    exclude_loss: true            # PE<0 剔除；PE 缺失不剔除
    name_blacklist: ["ST", "*ST", "退"]
  us:
    min_listing_days: 20
    min_turnover_amt: 50000000    # $5000万
    min_price: 2.0
    exclude_loss: true
    name_blacklist: []
scoring:
  weights: {finance: 0.4, technical: 0.3, flow: 0.3}
advisor:
  capital_base: 100000            # 默认本金，Web/.env 可覆盖
  risk_profiles:
    conservative: {max_pos: 0.10, max_industry: 0.30, min_cash: 0.50, n_picks: 3}
    balanced:     {max_pos: 0.15, max_industry: 0.30, min_cash: 0.30, n_picks: 4}
    aggressive:   {max_pos: 0.25, max_industry: 0.30, min_cash: 0.10, n_picks: 6}
```

```python
# screener/filters.py
from __future__ import annotations
from pathlib import Path
import yaml

_DEFAULT_CFG = Path(__file__).resolve().parent.parent / "config" / "sgod.yaml"

def load_sgod_config(path=None) -> dict:
    p = Path(path) if path else _DEFAULT_CFG
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def hard_filter(rows, market, cfg) -> list:
    mc = cfg["screener"][market]
    subnew_max = cfg["screener"]["subnew_max_days"]
    kept = []
    for r in rows:
        name = str(r.get("name") or "")
        if any(b in name for b in mc["name_blacklist"]):
            continue
        price = r.get("price")
        if price is None or price < mc["min_price"]:
            continue
        amt = r.get("turnover_amt")
        if amt is None or amt < mc["min_turnover_amt"]:
            continue
        pe = r.get("pe")
        if mc["exclude_loss"] and pe is not None and pe < 0:
            continue
        days = r.get("listing_days")
        if days is not None and days < mc["min_listing_days"]:
            continue
        tags = list(r.get("tags") or [])
        if days is not None and days <= subnew_max:
            tags.append("次新")
        kept.append({**r, "tags": tags})
    return kept
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests_sgod/test_filters.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add screener/filters.py config/sgod.yaml tests_sgod/test_filters.py
git commit -m "feat(sgod): 硬条件过滤+可调参数配置(次新打标不剔除)"
```

---

### Task 3: 三维量化打分 `screener/scoring.py`

**Files:**
- Create: `screener/scoring.py`
- Test: `tests_sgod/test_scoring.py`

**Interfaces:**
- Consumes: Task 2 过滤后的行
- Produces: `score_row(row: dict, cfg: dict) -> dict` — 返回 `{**row, "score": float(0-100), "score_parts": {"finance": f, "technical": f, "flow": f}}`；`rank_top(rows, cfg, exclude_codes: set) -> list[dict]` — 按 score 降序取 `top_n`，排除 `exclude_codes`（去重用）。子分缺数据时该维记 50 分（中性，不奖不罚）。

- [ ] **Step 1: 写失败测试**

```python
# tests_sgod/test_scoring.py
from screener.filters import load_sgod_config
from screener.scoring import score_row, rank_top

CFG = load_sgod_config()

def _row(**kw):
    base = {"code": "600000", "name": "样本", "market": "a", "price": 10.0,
            "pct_chg": 1.0, "turnover_amt": 5e8, "volume_ratio": 1.2,
            "turnover_rate": 3.0, "pe": 15.0, "pb": 1.5, "total_mv": 3e10,
            "circ_mv": 3e10, "pct_60d": 8.0, "listing_days": 1000, "tags": []}
    base.update(kw)
    return base

def test_score_in_range_and_has_parts():
    s = score_row(_row(), CFG)
    assert 0 <= s["score"] <= 100
    assert set(s["score_parts"]) == {"finance", "technical", "flow"}

def test_missing_data_scores_neutral_50():
    s = score_row(_row(pe=None, pb=None), CFG)
    assert s["score_parts"]["finance"] == 50.0

def test_reasonable_ordering():
    good = score_row(_row(pe=12, pb=1.2, pct_60d=12, volume_ratio=1.8,
                          turnover_rate=5.0), CFG)
    bad = score_row(_row(pe=200, pb=20, pct_60d=-30, volume_ratio=0.3,
                         turnover_rate=0.2), CFG)
    assert good["score"] > bad["score"]

def test_rank_top_excludes_and_limits():
    rows = [score_row(_row(code=f"6000{i:02d}"), CFG) for i in range(30)]
    top = rank_top(rows, CFG, exclude_codes={"600001", "600002"})
    assert len(top) == CFG["screener"]["top_n"]
    assert all(r["code"] not in {"600001", "600002"} for r in top)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests_sgod/test_scoring.py -v`
Expected: FAIL

- [ ] **Step 3: 最小实现**

```python
# screener/scoring.py
# 三维打分：每维 0-100，缺数据记 50（中性）。分段线性打分，阈值就近取材于
# A股/美股常识区间；细调只改这里的表，不改结构。
from __future__ import annotations

def _piecewise(v, points):
    """points: [(x0,y0),(x1,y1),...] 单调 x；v 超界取端点分。v=None → None"""
    if v is None:
        return None
    pts = sorted(points)
    if v <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if v <= x1:
            return y0 + (y1 - y0) * (v - x0) / (x1 - x0)
    return pts[-1][1]

def _avg(vals):
    vs = [v for v in vals if v is not None]
    return sum(vs) / len(vs) if vs else None

def _finance_score(r):
    pe = _piecewise(r.get("pe"), [(5, 90), (15, 100), (30, 70), (60, 40), (120, 10)])
    pb = _piecewise(r.get("pb"), [(0.5, 80), (1.5, 100), (5, 60), (15, 20)])
    return _avg([pe, pb])

def _technical_score(r):
    mom = _piecewise(r.get("pct_60d"), [(-30, 10), (-5, 40), (5, 70), (25, 100), (60, 60)])
    chg = _piecewise(r.get("pct_chg"), [(-9, 20), (0, 60), (4, 100), (9, 50)])
    return _avg([mom, chg])

def _flow_score(r):
    vr = _piecewise(r.get("volume_ratio"), [(0.3, 20), (1.0, 60), (2.0, 100), (5.0, 40)])
    tr = _piecewise(r.get("turnover_rate"), [(0.2, 30), (2, 80), (7, 100), (20, 30)])
    return _avg([vr, tr])

def score_row(row: dict, cfg: dict) -> dict:
    parts = {"finance": _finance_score(row), "technical": _technical_score(row),
             "flow": _flow_score(row)}
    parts = {k: (50.0 if v is None else round(v, 1)) for k, v in parts.items()}
    w = cfg["scoring"]["weights"]
    score = sum(parts[k] * w[k] for k in parts)
    return {**row, "score": round(score, 1), "score_parts": parts}

def rank_top(rows, cfg, exclude_codes=frozenset()):
    pool = [r for r in rows if r["code"] not in exclude_codes]
    pool.sort(key=lambda r: r["score"], reverse=True)
    return pool[: cfg["screener"]["top_n"]]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests_sgod/test_scoring.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add screener/scoring.py tests_sgod/test_scoring.py
git commit -m "feat(sgod): 三维量化打分(财务/技术/资金,缺数据中性50)"
```

---

### Task 4: 推荐历史与新面孔去重 `screener/history.py`

**Files:**
- Create: `screener/history.py`
- Test: `tests_sgod/test_history.py`

**Interfaces:**
- Produces: `class RecommendHistory(db_path)` — 方法：`recent_codes(market: str, days: int) -> set[str]`；`record(market: str, codes: list[str], day: str) -> None`（day 格式 `YYYY-MM-DD`）。stdlib sqlite3，建表语句内置，幂等。

- [ ] **Step 1: 写失败测试**

```python
# tests_sgod/test_history.py
from screener.history import RecommendHistory

def test_record_and_recent(tmp_path):
    h = RecommendHistory(tmp_path / "h.db")
    h.record("a", ["600519", "000858"], "2026-07-28")
    h.record("a", ["600519"], "2026-07-01")   # 旧记录
    h.record("us", ["AAPL"], "2026-07-28")
    recent = h.recent_codes("a", days=14)
    assert "600519" in recent and "000858" in recent
    assert "AAPL" not in recent               # 市场隔离

def test_old_records_expire(tmp_path):
    h = RecommendHistory(tmp_path / "h.db")
    h.record("a", ["600000"], "2020-01-01")
    assert h.recent_codes("a", days=14) == set()

def test_idempotent_same_day(tmp_path):
    h = RecommendHistory(tmp_path / "h.db")
    h.record("a", ["600519"], "2026-07-28")
    h.record("a", ["600519"], "2026-07-28")   # 重复写不报错
    assert h.recent_codes("a", days=14) == {"600519"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests_sgod/test_history.py -v`
Expected: FAIL

- [ ] **Step 3: 最小实现**

```python
# screener/history.py
from __future__ import annotations
import sqlite3
from datetime import date, timedelta
from pathlib import Path

class RecommendHistory:
    def __init__(self, db_path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS recommend_history ("
            "market TEXT NOT NULL, code TEXT NOT NULL, day TEXT NOT NULL,"
            "PRIMARY KEY (market, code, day))")
        self.conn.commit()

    def recent_codes(self, market: str, days: int) -> set:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        rows = self.conn.execute(
            "SELECT code FROM recommend_history WHERE market=? AND day>=?",
            (market, cutoff)).fetchall()
        return {r[0] for r in rows}

    def record(self, market: str, codes, day: str) -> None:
        self.conn.executemany(
            "INSERT OR IGNORE INTO recommend_history VALUES (?,?,?)",
            [(market, c, day) for c in codes])
        self.conn.commit()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests_sgod/test_history.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add screener/history.py tests_sgod/test_history.py
git commit -m "feat(sgod): 推荐历史SQLite——14天新面孔去重"
```

---

### Task 5: 量化买点 `screener/buypoint.py`

**Files:**
- Create: `screener/buypoint.py`
- Test: `tests_sgod/test_buypoint.py`

**Interfaces:**
- Consumes: 近 60 日日 K `list[dict]`，每项 `{"close": f, "high": f, "low": f, "volume": f}`（旧→新排序）
- Produces: `buy_zone(klines: list[dict], last_price: float) -> dict | None` — 返回 `{"support": f, "resistance": f, "ma20": f, "buy_low": f, "buy_high": f, "trigger": str, "position_hint": str}`；K 线不足 20 根返回 `None`。

- [ ] **Step 1: 写失败测试**

```python
# tests_sgod/test_buypoint.py
from screener.buypoint import buy_zone

def _k(closes):
    return [{"close": c, "high": c * 1.02, "low": c * 0.98, "volume": 1e6}
            for c in closes]

def test_insufficient_klines_returns_none():
    assert buy_zone(_k([10.0] * 10), 10.0) is None

def test_uptrend_zone_between_support_and_price():
    closes = [10 + i * 0.1 for i in range(60)]     # 稳步上行
    z = buy_zone(_k(closes), closes[-1])
    assert z["support"] < z["buy_low"] <= z["buy_high"] <= z["resistance"]
    assert z["buy_high"] <= closes[-1] * 1.01      # 不追高：买点不高于现价+1%
    assert "回踩" in z["trigger"] or "突破" in z["trigger"]

def test_overextended_price_suggests_wait():
    closes = [10.0] * 50 + [10.5, 11.5, 12.8, 14.2, 16.0]   # 短期暴涨乖离大
    z = buy_zone(_k(closes), 16.0)
    assert z["position_hint"] == "观望"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests_sgod/test_buypoint.py -v`
Expected: FAIL

- [ ] **Step 3: 最小实现**

```python
# screener/buypoint.py
# 量化买点：支撑=近20日低点与MA20较高者，压力=近60日高点，
# 买入区间=[支撑, min(MA5, 现价*1.01)]。乖离率(现价/MA20-1)>8% → 观望。
# 上游交易理念对齐：不追高、缩量回踩均线是首选买点。
from __future__ import annotations

def _ma(closes, n):
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n

def buy_zone(klines, last_price):
    if not klines or len(klines) < 20 or last_price is None:
        return None
    closes = [k["close"] for k in klines]
    lows = [k["low"] for k in klines]
    highs = [k["high"] for k in klines]
    ma5, ma20 = _ma(closes, 5), _ma(closes, 20)
    support = max(min(lows[-20:]), ma20) if ma20 else min(lows[-20:])
    resistance = max(highs[-60:] if len(highs) >= 60 else highs)
    bias = (last_price / ma20 - 1) if ma20 else 0.0
    buy_high = min(ma5 or last_price, last_price * 1.01)
    buy_low = min(support, buy_high)
    if bias > 0.08:
        hint, trigger = "观望", "乖离率过大，等回踩 MA20 缩量企稳再介入"
    elif last_price <= buy_high:
        hint, trigger = "标准", "现价处于买入区间，回踩支撑缩量企稳可分批介入"
    else:
        hint, trigger = "轻仓试探", "等回踩 MA5/MA10 或放量突破压力位后回抽确认"
    return {"support": round(support, 2), "resistance": round(resistance, 2),
            "ma20": round(ma20, 2) if ma20 else None,
            "buy_low": round(buy_low, 2), "buy_high": round(buy_high, 2),
            "trigger": trigger, "position_hint": hint}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests_sgod/test_buypoint.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add screener/buypoint.py tests_sgod/test_buypoint.py
git commit -m "feat(sgod): 量化买点——支撑压力/买入区间/乖离观望"
```

---

### Task 6: 快照拉取与初筛编排 `screener/snapshot.py` + `screener/run.py`

**Files:**
- Create: `screener/snapshot.py`
- Create: `screener/run.py`
- Test: `tests_sgod/test_screener_run.py`

**Interfaces:**
- Produces（snapshot.py）: `fetch_snapshot(market: str) -> list[dict]`（已 normalize；A股：`ak.stock_zh_a_spot_em()`；美股：`ak.stock_us_spot_em()`；重试 3 次指数退避，最终失败抛 `SnapshotError`）；`fetch_listing_days_a(codes) -> dict[str, int]`（`ak.stock_zh_a_new_em` 之外用 `ak.stock_individual_info_em` 仅对通过初筛的 Top50 补上市天数，减少调用）；`fetch_klines(code, market, days=60) -> list[dict]`（A股 `ak.stock_zh_a_hist`，美股 `ak.stock_us_hist`，normalize 为 buypoint 输入格式）
- Produces（run.py）: `run_screener(market: str, cfg: dict, history: RecommendHistory, top_n=None) -> list[dict]` — 完整初筛：fetch→filter→score→取 Top50→补上市天数与二次过滤→dedup→Top20→逐只补 K 线与 `buy_zone` → 返回带 `buy` 字段的候选列表；`main()` CLI：`python -m screener.run --market a --dry-run`
- 测试策略：`fetch_*` 用 monkeypatch 打桩，`run_screener` 全流程不碰网络

- [ ] **Step 1: 写失败测试**

```python
# tests_sgod/test_screener_run.py
import screener.run as srun
from screener.filters import load_sgod_config
from screener.history import RecommendHistory

CFG = load_sgod_config()

def _fake_snapshot(market):
    rows = []
    for i in range(40):
        rows.append({"code": f"6001{i:02d}", "name": f"股{i}", "market": "a",
                     "price": 10.0 + i, "pct_chg": 1.0, "turnover_amt": 5e8,
                     "volume_ratio": 1.2, "turnover_rate": 3.0, "pe": 10 + i,
                     "pb": 1.5, "total_mv": 3e10, "circ_mv": 3e10,
                     "pct_60d": 5.0, "listing_days": None})
    return rows

def _fake_listing_days(codes):
    return {c: 500 for c in codes}

def _fake_klines(code, market, days=60):
    return [{"close": 10 + i * 0.05, "high": 10.3 + i * 0.05,
             "low": 9.8 + i * 0.05, "volume": 1e6} for i in range(60)]

def test_run_screener_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(srun, "fetch_snapshot", _fake_snapshot)
    monkeypatch.setattr(srun, "fetch_listing_days_a", _fake_listing_days)
    monkeypatch.setattr(srun, "fetch_klines", _fake_klines)
    h = RecommendHistory(tmp_path / "h.db")
    h.record("a", ["600139"], "2026-07-28")  # 最高分之一提前进历史
    top = srun.run_screener("a", CFG, h)
    assert len(top) == CFG["screener"]["top_n"]
    assert all(r["code"] != "600139" for r in top)      # 去重生效
    assert all("buy" in r and r["buy"] for r in top)     # 每只带买点
    assert all("score" in r for r in top)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests_sgod/test_screener_run.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 snapshot.py（薄网络层）与 run.py**

```python
# screener/snapshot.py
from __future__ import annotations
import time
from .norm import normalize_row, to_float

class SnapshotError(RuntimeError):
    pass

def _retry(fn, tries=3, base=2.0):
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:      # 网络层唯一允许宽捕获的地方
            last = e
            time.sleep(base * (2 ** i))
    raise SnapshotError(str(last))

def fetch_snapshot(market: str):
    import akshare as ak
    if market == "a":
        df = _retry(lambda: ak.stock_zh_a_spot_em())
    elif market == "us":
        df = _retry(lambda: ak.stock_us_spot_em())
    else:
        raise ValueError(f"unknown market: {market}")
    return [normalize_row(row, market) for row in df.to_dict("records")]

def fetch_listing_days_a(codes):
    """仅对短名单逐只补上市天数；单只失败记 None 不阻塞。"""
    import akshare as ak
    from datetime import date
    out = {}
    for c in codes:
        try:
            info = ak.stock_individual_info_em(symbol=c)
            kv = dict(zip(info["item"], info["value"]))
            d = str(kv.get("上市时间") or "")
            if len(d) == 8 and d.isdigit():
                y, m, dd = int(d[:4]), int(d[4:6]), int(d[6:])
                out[c] = (date.today() - date(y, m, dd)).days
            else:
                out[c] = None
        except Exception:
            out[c] = None
        time.sleep(0.3)             # 限流保护
    return out

def fetch_klines(code, market, days=60):
    import akshare as ak
    try:
        if market == "a":
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq").tail(days)
            cols = {"收盘": "close", "最高": "high", "最低": "low", "成交量": "volume"}
        else:
            df = ak.stock_us_hist(symbol=code, period="daily", adjust="qfq").tail(days)
            cols = {"收盘": "close", "最高": "high", "最低": "low", "成交量": "volume"}
        recs = df.rename(columns=cols).to_dict("records")
        return [{k: to_float(r.get(k)) for k in ("close", "high", "low", "volume")}
                for r in recs]
    except Exception:
        return []
```

```python
# screener/run.py
from __future__ import annotations
import argparse, json
from pathlib import Path
from .filters import hard_filter, load_sgod_config
from .scoring import score_row, rank_top
from .history import RecommendHistory
from .buypoint import buy_zone
from .snapshot import fetch_snapshot, fetch_listing_days_a, fetch_klines

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "sgod" / "history.db"

def run_screener(market, cfg, history, top_n=None):
    rows = fetch_snapshot(market)
    kept = hard_filter(rows, market, cfg)
    scored = [score_row(r, cfg) for r in kept]
    scored.sort(key=lambda r: r["score"], reverse=True)
    short = scored[:50]                                   # 短名单再精查
    if market == "a":
        days_map = fetch_listing_days_a([r["code"] for r in short])
        for r in short:
            r["listing_days"] = days_map.get(r["code"])
        short = hard_filter(short, market, cfg)           # 二次过滤(补齐天数后)
        short = [score_row(r, cfg) for r in short]
    exclude = history.recent_codes(market, cfg["screener"]["dedup_days"])
    if top_n:
        cfg = {**cfg, "screener": {**cfg["screener"], "top_n": top_n}}
    top = rank_top(short, cfg, exclude_codes=exclude)
    for r in top:
        r["buy"] = buy_zone(fetch_klines(r["code"], market), r["price"])
    return top

def main():
    p = argparse.ArgumentParser(description="选股神器·全市场初筛")
    p.add_argument("--market", choices=("a", "us"), required=True)
    p.add_argument("--dry-run", action="store_true", help="只打印不写历史")
    p.add_argument("--top", type=int, default=None)
    args = p.parse_args()
    cfg = load_sgod_config()
    h = RecommendHistory(DB_PATH)
    top = run_screener(args.market, cfg, h, top_n=args.top)
    print(json.dumps([{k: r[k] for k in ("code", "name", "score", "tags", "buy")}
                      for r in top], ensure_ascii=False, indent=2))
    if not args.dry_run:
        from datetime import date
        h.record(args.market, [r["code"] for r in top], date.today().isoformat())

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests_sgod/test_screener_run.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: 真实冒烟（本机需网络，允许失败不阻塞提交）**

Run: `python -m screener.run --market a --dry-run --top 5`
Expected: 打印 5 只 A股 JSON（含 score/buy）；若网络受限记录输出留档

- [ ] **Step 6: Commit**

```bash
git add screener/snapshot.py screener/run.py tests_sgod/test_screener_run.py
git commit -m "feat(sgod): 快照拉取+初筛编排CLI(两级漏斗/去重/买点)"
```

---

### Task 7: IMDS 三卡比率计算 `imds_finance/ratios.py`

**Files:**
- Create: `imds_finance/__init__.py`（空文件）
- Create: `imds_finance/ratios.py`
- Test: `tests_sgod/test_imds_ratios.py`

**Interfaces:**
- Consumes: 季度财务序列 `list[dict]`（旧→新），每项字段（缺失为 None）：`{"period": "2026Q1", "revenue": f, "net_profit": f, "gross_profit": f, "op_cashflow": f, "total_assets": f, "total_liab": f, "equity": f, "ar": f, "inventory": f, "goodwill": f, "current_assets": f, "current_liab": f, "sales_exp": f, "admin_exp": f, "fin_exp": f, "rd_exp": f}`
- Produces:
  - `peer_card(series) -> dict`：`{"gross_margin": %, "net_margin": %, "roe": %, "debt_ratio": %, "inv_turnover": x, "asset_turnover": x, "ar_turnover": x}`（TTM 口径：最近 4 季合计 / 期末或平均值；对齐 cxodex-finance-app peer.js——比率百分数、周转率倍数）
  - `mgmt_card(series) -> dict`：`{"cash_quality": f(经营现金流TTM/净利TTM), "expense_rates": {"sales": %, "admin": %, "fin": %, "rd": %}, "rev_yoy": %, "profit_yoy": %, "growth_match": "利润快于收入"|"收入快于利润"|"同步"|None}`
  - `risk_card(series) -> dict`：`{"current_ratio": f, "quick_ratio": f, "ar_vs_rev_gap": pp(应收增速-营收增速), "inv_vs_rev_gap": pp, "goodwill_ratio": %(商誉/净资产)}`
  - 全部：数据不足 → 对应值 None；除数为 0/None → None

- [ ] **Step 1: 写失败测试**

```python
# tests_sgod/test_imds_ratios.py
from imds_finance.ratios import peer_card, mgmt_card, risk_card

def _q(period, rev, profit, **kw):
    base = {"period": period, "revenue": rev, "net_profit": profit,
            "gross_profit": rev * 0.4, "op_cashflow": profit * 1.1,
            "total_assets": 1000.0, "total_liab": 400.0, "equity": 600.0,
            "ar": 100.0, "inventory": 80.0, "goodwill": 30.0,
            "current_assets": 500.0, "current_liab": 250.0,
            "sales_exp": rev * 0.05, "admin_exp": rev * 0.04,
            "fin_exp": rev * 0.01, "rd_exp": rev * 0.03}
    base.update(kw)
    return base

SERIES = [_q(f"202{y}Q{q}", 100.0 + i * 5, 10.0 + i)
          for i, (y, q) in enumerate((y, q) for y in (4, 5) for q in range(1, 5))]

def test_peer_card_ttm():
    c = peer_card(SERIES)
    assert abs(c["gross_margin"] - 40.0) < 0.5     # 毛利率恒 40%
    assert c["debt_ratio"] == 40.0                 # 400/1000
    assert c["roe"] is not None and c["inv_turnover"] is not None

def test_mgmt_card_growth_and_cash():
    c = mgmt_card(SERIES)
    assert c["cash_quality"] and abs(c["cash_quality"] - 1.1) < 0.01
    assert c["rev_yoy"] is not None and c["rev_yoy"] > 0
    assert c["expense_rates"]["rd"] is not None

def test_risk_card_ratios():
    c = risk_card(SERIES)
    assert c["current_ratio"] == 2.0               # 500/250
    assert c["goodwill_ratio"] == 5.0              # 30/600

def test_insufficient_data_returns_none_fields():
    c = peer_card(SERIES[:2])                      # 不足4季无TTM
    assert c["gross_margin"] is None
    c2 = mgmt_card(SERIES[:5])                     # 不足8季无YoY
    assert c2["rev_yoy"] is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests_sgod/test_imds_ratios.py -v`
Expected: FAIL

- [ ] **Step 3: 最小实现**

```python
# imds_finance/ratios.py
# IMDS 三卡口径（对齐 cxodex-finance-app）：比率返回百分数数值(46.9=46.9%)，
# 周转率返回倍数。TTM=最近4季合计；YoY=最近4季 vs 上4季。数据不够→None。
from __future__ import annotations

def _sum_last(series, key, n=4, offset=0):
    seg = series[len(series) - n - offset: len(series) - offset]
    if len(seg) < n:
        return None
    vals = [q.get(key) for q in seg]
    if any(v is None for v in vals):
        return None
    return sum(vals)

def _last(series, key):
    return series[-1].get(key) if series else None

def _div(a, b, pct=False):
    if a is None or b is None or b == 0:
        return None
    v = a / b
    return round(v * 100, 1) if pct else round(v, 2)

def _yoy(series, key):
    cur, prev = _sum_last(series, key, 4, 0), _sum_last(series, key, 4, 4)
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur / abs(prev) - 1) * 100, 1)

def peer_card(series) -> dict:
    rev, gp, np_ = (_sum_last(series, k) for k in ("revenue", "gross_profit", "net_profit"))
    cogs = (rev - gp) if (rev is not None and gp is not None) else None
    return {"gross_margin": _div(gp, rev, pct=True),
            "net_margin": _div(np_, rev, pct=True),
            "roe": _div(np_, _last(series, "equity"), pct=True),
            "debt_ratio": _div(_last(series, "total_liab"), _last(series, "total_assets"), pct=True),
            "inv_turnover": _div(cogs, _last(series, "inventory")),
            "asset_turnover": _div(rev, _last(series, "total_assets")),
            "ar_turnover": _div(rev, _last(series, "ar"))}

def mgmt_card(series) -> dict:
    rev, np_, ocf = (_sum_last(series, k) for k in ("revenue", "net_profit", "op_cashflow"))
    rates = {k: _div(_sum_last(series, f"{k}_exp"), rev, pct=True)
             for k in ("sales", "admin", "fin", "rd")}
    rev_yoy, profit_yoy = _yoy(series, "revenue"), _yoy(series, "net_profit")
    match = None
    if rev_yoy is not None and profit_yoy is not None:
        d = profit_yoy - rev_yoy
        match = "利润快于收入" if d > 5 else ("收入快于利润" if d < -5 else "同步")
    return {"cash_quality": _div(ocf, np_), "expense_rates": rates,
            "rev_yoy": rev_yoy, "profit_yoy": profit_yoy, "growth_match": match}

def risk_card(series) -> dict:
    ca, cl = _last(series, "current_assets"), _last(series, "current_liab")
    inv = _last(series, "inventory")
    quick = None
    if ca is not None and cl not in (None, 0) and inv is not None:
        quick = round((ca - inv) / cl, 2)
    def _gap(key):
        g, r = _yoy(series, key), _yoy(series, "revenue")
        return round(g - r, 1) if (g is not None and r is not None) else None
    return {"current_ratio": _div(ca, cl),
            "quick_ratio": quick,
            "ar_vs_rev_gap": _gap("ar"),
            "inv_vs_rev_gap": _gap("inventory"),
            "goodwill_ratio": _div(_last(series, "goodwill"), _last(series, "equity"), pct=True)}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests_sgod/test_imds_ratios.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add imds_finance/ tests_sgod/test_imds_ratios.py
git commit -m "feat(sgod): IMDS三卡比率计算(同行/管理层/风险,TTM口径)"
```

---

### Task 8: 财务健康评分 `imds_finance/scoring.py`

**Files:**
- Create: `imds_finance/scoring.py`
- Test: `tests_sgod/test_imds_scoring.py`

**Interfaces:**
- Consumes: Task 7 三卡 dict + 可选同行中位数 `peer_median: dict | None`（peer_card 同构）
- Produces: `health_score(peer: dict, mgmt: dict, risk: dict, peer_median=None) -> dict` — `{"score": float 0-100 | None, "coverage": float 0-1, "flags": list[str]}`。coverage = 参与打分的指标数/总指标数；coverage < 0.4 → score=None（数据不足不硬打分，即「次新降权」语义）。flags 收集异常（现金质量差/应收异增/商誉过高等）。

- [ ] **Step 1: 写失败测试**

```python
# tests_sgod/test_imds_scoring.py
from imds_finance.scoring import health_score

GOOD_PEER = {"gross_margin": 45.0, "net_margin": 20.0, "roe": 18.0,
             "debt_ratio": 35.0, "inv_turnover": 6.0, "asset_turnover": 0.8,
             "ar_turnover": 8.0}
GOOD_MGMT = {"cash_quality": 1.2, "expense_rates": {"sales": 5.0, "admin": 4.0,
             "fin": 1.0, "rd": 5.0}, "rev_yoy": 20.0, "profit_yoy": 25.0,
             "growth_match": "利润快于收入"}
GOOD_RISK = {"current_ratio": 2.0, "quick_ratio": 1.5, "ar_vs_rev_gap": 0.0,
             "inv_vs_rev_gap": -2.0, "goodwill_ratio": 5.0}

def test_good_company_scores_high():
    r = health_score(GOOD_PEER, GOOD_MGMT, GOOD_RISK)
    assert r["score"] is not None and r["score"] >= 70
    assert r["flags"] == []

def test_bad_signals_lower_score_and_flag():
    bad_mgmt = {**GOOD_MGMT, "cash_quality": 0.2}
    bad_risk = {**GOOD_RISK, "ar_vs_rev_gap": 30.0, "goodwill_ratio": 60.0}
    r = health_score(GOOD_PEER, bad_mgmt, bad_risk)
    good = health_score(GOOD_PEER, GOOD_MGMT, GOOD_RISK)
    assert r["score"] < good["score"]
    assert any("现金" in f for f in r["flags"])
    assert any("商誉" in f for f in r["flags"])

def test_insufficient_coverage_returns_none():
    empty = {k: None for k in GOOD_PEER}
    empty_m = {"cash_quality": None, "expense_rates": {k: None for k in
               ("sales", "admin", "fin", "rd")}, "rev_yoy": None,
               "profit_yoy": None, "growth_match": None}
    empty_r = {k: None for k in GOOD_RISK}
    r = health_score(empty, empty_m, empty_r)
    assert r["score"] is None and r["coverage"] < 0.4

def test_peer_median_comparison_adjusts_score():
    weak_median = {**GOOD_PEER, "gross_margin": 20.0, "roe": 8.0}
    vs_weak = health_score(GOOD_PEER, GOOD_MGMT, GOOD_RISK, peer_median=weak_median)
    vs_none = health_score(GOOD_PEER, GOOD_MGMT, GOOD_RISK)
    assert vs_weak["score"] >= vs_none["score"]    # 显著优于同行 → 加分
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests_sgod/test_imds_scoring.py -v`
Expected: FAIL

- [ ] **Step 3: 最小实现**

```python
# imds_finance/scoring.py
# 财务健康评分：指标→0-100 分段线性，加权平均；coverage<0.4 不打分。
# 同行中位数存在时：核心盈利指标显著优于中位数 +5、显著落后 -5（封顶100/0）。
from __future__ import annotations
from screener.scoring import _piecewise  # 复用分段线性

_SPECS = [
    # (取值函数, 分段表, 权重)
    (lambda p, m, r: p["gross_margin"], [(5, 20), (20, 55), (40, 85), (60, 100)], 1.0),
    (lambda p, m, r: p["net_margin"],   [(0, 25), (8, 60), (20, 90), (35, 100)], 1.0),
    (lambda p, m, r: p["roe"],          [(2, 20), (8, 55), (15, 85), (25, 100)], 1.5),
    (lambda p, m, r: p["debt_ratio"],   [(20, 95), (45, 75), (65, 45), (85, 10)], 1.0),
    (lambda p, m, r: m["cash_quality"], [(0.2, 15), (0.7, 55), (1.0, 85), (1.5, 100)], 1.5),
    (lambda p, m, r: m["rev_yoy"],      [(-20, 15), (0, 50), (15, 80), (40, 100)], 1.0),
    (lambda p, m, r: m["profit_yoy"],   [(-30, 10), (0, 50), (20, 85), (50, 100)], 1.0),
    (lambda p, m, r: r["current_ratio"],[(0.6, 15), (1.0, 50), (1.8, 90), (3.0, 100)], 0.8),
    (lambda p, m, r: r["ar_vs_rev_gap"],[(-10, 100), (5, 80), (20, 40), (40, 5)], 0.8),
    (lambda p, m, r: r["goodwill_ratio"],[(5, 100), (20, 75), (40, 40), (60, 10)], 0.7),
]

_FLAG_RULES = [
    (lambda p, m, r: m["cash_quality"] is not None and m["cash_quality"] < 0.5,
     "经营现金流质量差（现金流/净利<0.5）"),
    (lambda p, m, r: r["ar_vs_rev_gap"] is not None and r["ar_vs_rev_gap"] > 15,
     "应收账款增速显著快于营收，回款风险"),
    (lambda p, m, r: r["inv_vs_rev_gap"] is not None and r["inv_vs_rev_gap"] > 15,
     "存货增速显著快于营收，滞销风险"),
    (lambda p, m, r: r["goodwill_ratio"] is not None and r["goodwill_ratio"] > 40,
     "商誉/净资产过高，减值风险"),
    (lambda p, m, r: p["debt_ratio"] is not None and p["debt_ratio"] > 75,
     "资产负债率过高"),
]

def health_score(peer, mgmt, risk, peer_median=None) -> dict:
    scored, weights = [], []
    for get, table, w in _SPECS:
        v = get(peer, mgmt, risk)
        s = _piecewise(v, table)
        if s is not None:
            scored.append(s * w)
            weights.append(w)
    coverage = round(len(weights) / len(_SPECS), 2)
    flags = [msg for cond, msg in _FLAG_RULES if cond(peer, mgmt, risk)]
    if coverage < 0.4:
        return {"score": None, "coverage": coverage, "flags": flags}
    score = sum(scored) / sum(weights)
    if peer_median:
        for key in ("gross_margin", "roe"):
            a, b = peer.get(key), peer_median.get(key)
            if a is not None and b is not None and b != 0:
                if a > b * 1.3:
                    score += 2.5
                elif a < b * 0.7:
                    score -= 2.5
    return {"score": round(max(0.0, min(100.0, score)), 1),
            "coverage": coverage, "flags": flags}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests_sgod/test_imds_scoring.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add imds_finance/scoring.py tests_sgod/test_imds_scoring.py
git commit -m "feat(sgod): 财务健康评分(coverage门槛+异常flags+同行加减分)"
```

---

### Task 9: 财报适配器 `imds_finance/fetch.py`

**Files:**
- Create: `imds_finance/fetch.py`
- Test: `tests_sgod/test_imds_fetch.py`

**Interfaces:**
- Produces: `fetch_series(code: str, market: str, quarters=8) -> list[dict]`（Task 7 输入格式，旧→新；拿不到的字段 None；完全失败返回 `[]`）；`fetch_industry(code: str, market: str) -> str | None`（A股：`ak.stock_individual_info_em` 的行业；美股：yfinance `info["sector"]`）；`fetch_peer_median(industry: str, market: str) -> dict | None`（A股：`ak.stock_board_industry_cons_em` 成分股快照算中位数毛利率/ROE 近似；美股首版返回 None——不臆造）
- 内部：`_a_series(code, quarters)` 用 `ak.stock_financial_abstract(symbol)`（同花顺摘要，含营收/净利/毛利/现金流/资产负债表科目）+ 同义词映射；`_us_series` 用 `yfinance.Ticker(code).quarterly_financials / quarterly_balance_sheet / quarterly_cashflow` + 英文科目映射
- 测试：适配器的**映射与拼装逻辑**用 fixture DataFrame 测试（monkeypatch akshare/yfinance），不做真实网络断言

- [ ] **Step 1: 写失败测试**

```python
# tests_sgod/test_imds_fetch.py
import pandas as pd
import imds_finance.fetch as ff

def test_a_series_maps_synonyms(monkeypatch):
    df = pd.DataFrame({
        "选项": ["常用指标"] * 4,
        "指标": ["营业总收入", "归母净利润", "经营现金流量净额", "资产负债率"],
        "20260331": [100.0, 10.0, 12.0, 40.0],
        "20251231": [95.0, 9.0, 11.0, 41.0],
    })
    monkeypatch.setattr(ff, "_ak_financial_abstract", lambda code: df)
    series = ff._a_series("600519", quarters=8)
    assert len(series) == 2
    assert series[-1]["period"] == "20260331"      # 旧→新排序
    assert series[-1]["revenue"] == 100.0
    assert series[-1]["net_profit"] == 10.0
    assert series[-1]["gross_profit"] is None      # fixture 没给 → None

def test_fetch_series_total_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(ff, "_ak_financial_abstract",
                        lambda code: (_ for _ in ()).throw(RuntimeError("网络挂了")))
    assert ff.fetch_series("600519", "a") == []

def test_us_series_maps_yf_frames(monkeypatch):
    fin = pd.DataFrame({pd.Timestamp("2026-03-31"): {"Total Revenue": 100.0,
                        "Net Income": 10.0, "Gross Profit": 40.0},
                        pd.Timestamp("2025-12-31"): {"Total Revenue": 95.0,
                        "Net Income": 9.0, "Gross Profit": 38.0}})
    bal = pd.DataFrame({pd.Timestamp("2026-03-31"): {"Total Assets": 1000.0,
                        "Total Liabilities Net Minority Interest": 400.0,
                        "Stockholders Equity": 600.0}})
    cf = pd.DataFrame({pd.Timestamp("2026-03-31"): {"Operating Cash Flow": 12.0}})
    monkeypatch.setattr(ff, "_yf_frames", lambda code: (fin, bal, cf))
    series = ff._us_series("AAPL", quarters=8)
    assert series[-1]["revenue"] == 100.0
    assert series[-1]["total_assets"] == 1000.0
    assert series[-1]["op_cashflow"] == 12.0
    assert series[0]["total_assets"] is None       # 早期季度资产表缺 → None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests_sgod/test_imds_fetch.py -v`
Expected: FAIL

- [ ] **Step 3: 实现（关键：所有外部调用包一层可 monkeypatch 的私有函数）**

```python
# imds_finance/fetch.py
# 财报适配器：A股走 akshare 财务摘要，美股走 yfinance 三表。
# 列名/科目名全部走同义词映射，映射不到→None；整体失败→[]。
from __future__ import annotations
from screener.norm import to_float

_A_SYNONYMS = {
    "revenue": ["营业总收入", "营业收入"],
    "net_profit": ["归母净利润", "净利润"],
    "gross_profit": ["毛利润", "毛利"],
    "op_cashflow": ["经营现金流量净额", "经营活动产生的现金流量净额"],
    "total_assets": ["总资产", "资产总计"],
    "total_liab": ["总负债", "负债合计"],
    "equity": ["股东权益合计", "归母股东权益", "所有者权益合计"],
    "ar": ["应收账款"],
    "inventory": ["存货"],
    "goodwill": ["商誉"],
    "current_assets": ["流动资产合计"],
    "current_liab": ["流动负债合计"],
    "sales_exp": ["销售费用"],
    "admin_exp": ["管理费用"],
    "fin_exp": ["财务费用"],
    "rd_exp": ["研发费用"],
}
_US_SYNONYMS = {
    "revenue": ["Total Revenue"], "net_profit": ["Net Income"],
    "gross_profit": ["Gross Profit"],
    "op_cashflow": ["Operating Cash Flow", "Total Cash From Operating Activities"],
    "total_assets": ["Total Assets"],
    "total_liab": ["Total Liabilities Net Minority Interest", "Total Liab"],
    "equity": ["Stockholders Equity", "Total Stockholder Equity"],
    "ar": ["Accounts Receivable"], "inventory": ["Inventory"],
    "goodwill": ["Goodwill"], "current_assets": ["Current Assets"],
    "current_liab": ["Current Liabilities"],
    "sales_exp": [], "admin_exp": ["Selling General And Administration"],
    "fin_exp": ["Interest Expense"], "rd_exp": ["Research And Development"],
}
_FIELDS = list(_A_SYNONYMS)

def _ak_financial_abstract(code):
    import akshare as ak
    return ak.stock_financial_abstract(symbol=code)

def _yf_frames(code):
    import yfinance as yf
    t = yf.Ticker(code)
    return t.quarterly_financials, t.quarterly_balance_sheet, t.quarterly_cashflow

def _a_series(code, quarters=8):
    df = _ak_financial_abstract(code)
    period_cols = [c for c in df.columns if str(c).isdigit() and len(str(c)) == 8]
    period_cols = sorted(period_cols)[-quarters:]
    by_indicator = {str(r["指标"]).strip(): r for _, r in df.iterrows()}
    def _val(key, col):
        for syn in _A_SYNONYMS[key]:
            if syn in by_indicator:
                return to_float(by_indicator[syn].get(col))
        return None
    return [{"period": str(c), **{k: _val(k, c) for k in _FIELDS}}
            for c in period_cols]

def _us_series(code, quarters=8):
    fin, bal, cf = _yf_frames(code)
    frames = {"fin": fin, "bal": bal, "cf": cf}
    cols = sorted({c for f in frames.values() for c in getattr(f, "columns", [])})
    cols = cols[-quarters:]
    def _val(key, col):
        for f in frames.values():
            for syn in _US_SYNONYMS[key]:
                if syn in getattr(f, "index", []) and col in f.columns:
                    return to_float(f.at[syn, col])
        return None
    return [{"period": str(getattr(c, "date", c)),
             **{k: _val(k, c) for k in _FIELDS}} for c in cols]

def fetch_series(code, market, quarters=8):
    try:
        return (_a_series if market == "a" else _us_series)(code, quarters)
    except Exception:
        return []

def fetch_industry(code, market):
    try:
        if market == "a":
            import akshare as ak
            info = ak.stock_individual_info_em(symbol=code)
            kv = dict(zip(info["item"], info["value"]))
            return str(kv.get("行业")) or None
        import yfinance as yf
        return yf.Ticker(code).info.get("sector")
    except Exception:
        return None

def fetch_peer_median(industry, market):
    if market != "a" or not industry:
        return None                     # 美股首版无同行中位数，不臆造
    try:
        import akshare as ak
        import statistics
        df = ak.stock_board_industry_cons_em(symbol=industry)
        def _med(col):
            vals = [to_float(v) for v in df.get(col, [])]
            vals = [v for v in vals if v is not None]
            return round(statistics.median(vals), 1) if len(vals) >= 5 else None
        return {"gross_margin": None, "net_margin": None,
                "roe": None, "debt_ratio": None,
                "pe_median": _med("市盈率-动态"), "pb_median": _med("市净率")}
    except Exception:
        return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests_sgod/test_imds_fetch.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add imds_finance/fetch.py tests_sgod/test_imds_fetch.py
git commit -m "feat(sgod): 财报适配器(A股akshare/美股yfinance,同义词映射)"
```

---

### Task 10: GLM 客户端 + 财务报告生成 `sgod/llm.py` + `imds_finance/report.py`

**Files:**
- Create: `sgod/__init__.py`（空文件）
- Create: `sgod/llm.py`
- Create: `imds_finance/report.py`
- Test: `tests_sgod/test_llm_and_report.py`

**Interfaces:**
- Produces（llm.py）: `chat(prompt: str, system: str = None, max_tokens=2000, temperature=0.4) -> str | None` — POST `{GLM_BASE_URL}/chat/completions`，model=`GLM_MODEL`，Bearer `GLM_API_KEY`；429/5xx 重试 3 次指数退避；最终失败返回 None（调用方降级为「AI 分析暂缺」）
- Produces（report.py）: `finance_report(code, name, market, series, industry=None, peer_median=None) -> dict` — `{"cards": {"peer":..., "mgmt":..., "risk":...}, "health": {...}, "analysis_text": str|None, "outlook_text": str|None}`；`build_prompt(...) -> str`（纯函数可测：三卡+评分+行业塞进提示词，要求 GLM 输出「管理层分析和关注」与「财务展望」两段）
- 测试：`build_prompt` 纯函数断言关键内容；`chat` 用 monkeypatch 打桩 `_post`

- [ ] **Step 1: 写失败测试**

```python
# tests_sgod/test_llm_and_report.py
import sgod.llm as llm
from imds_finance.report import build_prompt, finance_report

SERIES = [{"period": f"2025Q{q}", "revenue": 100.0 + q, "net_profit": 10.0,
           "gross_profit": 40.0, "op_cashflow": 11.0, "total_assets": 1000.0,
           "total_liab": 400.0, "equity": 600.0, "ar": 100.0, "inventory": 80.0,
           "goodwill": 30.0, "current_assets": 500.0, "current_liab": 250.0,
           "sales_exp": 5.0, "admin_exp": 4.0, "fin_exp": 1.0, "rd_exp": 3.0}
          for q in range(1, 5)] * 2

def test_build_prompt_contains_cards_and_asks_two_sections():
    p = build_prompt("600519", "贵州茅台", "a", SERIES, industry="白酒")
    assert "贵州茅台" in p and "白酒" in p
    assert "管理层分析和关注" in p and "财务展望" in p
    assert "毛利率" in p          # 三卡数据进了提示词

def test_chat_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr(llm, "_post", lambda *a, **k: None)
    assert llm.chat("hi") is None

def test_finance_report_degrades_without_llm(monkeypatch):
    import imds_finance.report as rep
    monkeypatch.setattr(rep, "chat", lambda *a, **k: None)
    r = finance_report("600519", "贵州茅台", "a", SERIES)
    assert r["health"]["score"] is not None
    assert r["analysis_text"] is None      # LLM 挂了不臆造文字
    assert r["cards"]["peer"]["gross_margin"] is not None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests_sgod/test_llm_and_report.py -v`
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# sgod/llm.py
from __future__ import annotations
import json, os, time
import requests

def _post(url, headers, payload, timeout=90):
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            return None
        resp.raise_for_status()
    except requests.RequestException:
        return None

def chat(prompt, system=None, max_tokens=2000, temperature=0.4):
    key = os.getenv("GLM_API_KEY")
    if not key:
        return None
    base = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
    model = os.getenv("GLM_MODEL", "glm-5.2")
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    payload = {"model": model, "messages": msgs,
               "max_tokens": max_tokens, "temperature": temperature}
    headers = {"Authorization": f"Bearer {key}"}
    for i in range(3):
        data = _post(f"{base}/chat/completions", headers, payload)
        if data:
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError):
                return None
        time.sleep(2 * (2 ** i))
    return None
```

```python
# imds_finance/report.py
from __future__ import annotations
import json
from .ratios import peer_card, mgmt_card, risk_card
from .scoring import health_score
from sgod.llm import chat

_SYSTEM = ("你是一名资深财务顾问，使用 IMDS 财务管理方法论（同行对比、管理层视角、"
           "风险扫描三张卡）解读上市公司财务。只依据给出的数据陈述，缺失的数据明确说"
           "「数据不足」，不得编造数字。")

def build_prompt(code, name, market, series, industry=None, peer_median=None) -> str:
    peer, mgmt, risk = peer_card(series), mgmt_card(series), risk_card(series)
    health = health_score(peer, mgmt, risk, peer_median)
    mkt = "A股" if market == "a" else "美股"
    return (
        f"{mkt}公司：{name}（{code}），行业：{industry or '未知'}。\n"
        f"同行对比卡（毛利率/净利率/ROE为百分数，周转率为倍数）：{json.dumps(peer, ensure_ascii=False)}\n"
        f"管理层视角卡：{json.dumps(mgmt, ensure_ascii=False)}\n"
        f"风险扫描卡：{json.dumps(risk, ensure_ascii=False)}\n"
        f"财务健康评分：{json.dumps(health, ensure_ascii=False)}\n"
        f"同行中位数（可能为空）：{json.dumps(peer_median, ensure_ascii=False)}\n\n"
        "请输出两节，用「### 管理层分析和关注」「### 财务展望」作小标题：\n"
        "1) 管理层分析和关注：当期盈利质量、费用结构、现金流与风险点，150字内；\n"
        "2) 财务展望：基于增速/毛利率方向/现金流走向对未来2-4个季度给出"
        "改善/恶化/平稳判断与2个关键观察指标，120字内。")

def _split_sections(text):
    if not text:
        return None, None
    a, o = None, None
    if "### 财务展望" in text:
        head, o = text.split("### 财务展望", 1)
        a = head.replace("### 管理层分析和关注", "").strip() or None
        o = o.strip() or None
    else:
        a = text.strip() or None
    return a, o

def finance_report(code, name, market, series, industry=None, peer_median=None):
    peer, mgmt, risk = peer_card(series), mgmt_card(series), risk_card(series)
    health = health_score(peer, mgmt, risk, peer_median)
    text = chat(build_prompt(code, name, market, series, industry, peer_median),
                system=_SYSTEM) if series else None
    analysis, outlook = _split_sections(text)
    return {"cards": {"peer": peer, "mgmt": mgmt, "risk": risk},
            "health": health, "analysis_text": analysis, "outlook_text": outlook}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests_sgod/test_llm_and_report.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add sgod/ imds_finance/report.py tests_sgod/test_llm_and_report.py
git commit -m "feat(sgod): GLM客户端+IMDS财务报告(分析与展望两节,LLM挂降级)"
```

---

### Task 11: 行业情报 `industry_intel/run.py`

**Files:**
- Create: `industry_intel/__init__.py`（空文件）
- Create: `industry_intel/run.py`
- Test: `tests_sgod/test_intel.py`

**Interfaces:**
- Consumes: 候选列表（含 `industry` 字段，Task 13 编排时由 `fetch_industry` 补上）
- Produces: `gather_intel(candidates: list[dict], market: str) -> dict` — `{industry: {"stocks": [codes], "news": [str], "assessment": str|None}}`；`build_queries(industry: str, market: str) -> list[str]`（纯函数：A股→行业政策/产业数据/贸易摩擦，美股→联储/CPI/关税/监管）；`_search(query) -> list[str]`（Tavily API，env `TAVILY_API_KEY`，无 Key 或失败返回 `[]`）；`build_intel_prompt(industry, news, stocks) -> str`（要求 GLM 输出：利好/利空/中性 + 影响时间窗 + 对候选股影响一句话）
- 每行业最多 2 次搜索、news 截取前 8 条标题；GLM 失败 → assessment=None

- [ ] **Step 1: 写失败测试**

```python
# tests_sgod/test_intel.py
import industry_intel.run as intel

def test_build_queries_market_specific():
    qa = intel.build_queries("半导体", "a")
    qus = intel.build_queries("Technology", "us")
    assert any("政策" in q for q in qa)
    assert any(("美联储" in q) or ("关税" in q) for q in qus)
    assert all(len(qs) <= 2 for qs in (qa, qus))

def test_gather_intel_groups_and_degrades(monkeypatch):
    monkeypatch.setattr(intel, "_search", lambda q: ["新闻标题1", "新闻标题2"])
    monkeypatch.setattr(intel, "chat", lambda *a, **k: "利好：……影响窗口1-2月")
    cands = [{"code": "600519", "industry": "白酒"},
             {"code": "000858", "industry": "白酒"},
             {"code": "300750", "industry": "电池"}]
    out = intel.gather_intel(cands, "a")
    assert set(out) == {"白酒", "电池"}
    assert out["白酒"]["stocks"] == ["600519", "000858"]
    assert out["白酒"]["assessment"].startswith("利好")

def test_no_search_key_returns_empty_news(monkeypatch):
    monkeypatch.setattr(intel, "_search", lambda q: [])
    monkeypatch.setattr(intel, "chat", lambda *a, **k: None)
    out = intel.gather_intel([{"code": "AAPL", "industry": "Technology"}], "us")
    assert out["Technology"]["news"] == []
    assert out["Technology"]["assessment"] is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests_sgod/test_intel.py -v`
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# industry_intel/run.py
from __future__ import annotations
import os
import requests
from sgod.llm import chat

def build_queries(industry, market):
    if market == "a":
        return [f"{industry} 行业政策 最新", f"{industry} 产业数据 出口 贸易"]
    return [f"{industry} sector Fed rates tariff policy impact",
            f"{industry} industry regulation news"]

def _search(query):
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return []
    try:
        resp = requests.post("https://api.tavily.com/search",
                             json={"api_key": key, "query": query,
                                   "max_results": 5, "days": 7},
                             timeout=30)
        resp.raise_for_status()
        return [r.get("title", "") for r in resp.json().get("results", []) if r.get("title")]
    except requests.RequestException:
        return []

def build_intel_prompt(industry, news, stocks):
    lines = "\n".join(f"- {n}" for n in news) or "（无新闻，仅按常识性宏观背景判断，明确标注不确定性）"
    return (f"行业：{industry}。近7天相关新闻标题：\n{lines}\n"
            f"该行业候选股：{', '.join(stocks)}。\n"
            "请判断：1) 总体利好/利空/中性；2) 影响时间窗（如1-2月/一季度）；"
            "3) 对候选股的影响一句话。共80字内，以「利好：/利空：/中性：」开头。")

def gather_intel(candidates, market):
    groups = {}
    for c in candidates:
        ind = c.get("industry") or "未知行业"
        groups.setdefault(ind, []).append(c["code"])
    out = {}
    for ind, codes in groups.items():
        news = []
        for q in build_queries(ind, market):
            news.extend(_search(q))
        news = news[:8]
        assessment = chat(build_intel_prompt(ind, news, codes)) if True else None
        out[ind] = {"stocks": codes, "news": news, "assessment": assessment}
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests_sgod/test_intel.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add industry_intel/ tests_sgod/test_intel.py
git commit -m "feat(sgod): 行业情报(分市场检索词/Tavily/GLM影响预测,全程可降级)"
```

---

### Task 12: 投资策略建议 `portfolio_advisor/`

**Files:**
- Create: `portfolio_advisor/__init__.py`（空文件）
- Create: `portfolio_advisor/allocate.py`
- Create: `portfolio_advisor/report.py`
- Test: `tests_sgod/test_advisor.py`

**Interfaces:**
- Consumes: 候选列表（含 `score`、`price`、`industry`、`buy`（Task 5 输出）、`health_score`（可 None））、`capital: float`、`profile: str`（conservative/balanced/aggressive）、cfg（Task 2 的 advisor 段）
- Produces（allocate.py）: `allocate(candidates, capital, profile, cfg) -> dict` —
  `{"picks": [{"code", "name", "amount": f, "weight": %, "shares": int|None, "first_batch": f, "add_batch": f, "buy": {...}}], "cash_reserve": f, "cash_pct": %}`。规则：综合排序 = `score × (health_score/100 或 0.8 当 None)`；单只 ≤ max_pos×capital；同行业合计 ≤ max_industry×capital；现金 ≥ min_cash×capital；选满 n_picks 或候选耗尽；A股 shares 取整到 100 股（买不起一手 → 剔除该股顺位递补）；美股按金额（shares=None）；first_batch=60% 金额、add_batch=40%（回踩加仓）
- Produces（report.py）: `advisor_report(alloc: dict, market: str) -> str | None` — GLM 生成组合逻辑说明（为何这么配/主要风险/止损调仓条件），失败 None；`build_advisor_prompt(alloc, market) -> str` 纯函数
- `position_hint == "观望"` 的候选不入选组合

- [ ] **Step 1: 写失败测试**

```python
# tests_sgod/test_advisor.py
from screener.filters import load_sgod_config
from portfolio_advisor.allocate import allocate
from portfolio_advisor.report import build_advisor_prompt

CFG = load_sgod_config()

def _cand(code, score, price, industry, hint="标准", health=80.0):
    return {"code": code, "name": f"N{code}", "score": score, "price": price,
            "market": "a", "industry": industry, "health_score": health,
            "buy": {"buy_low": price * 0.95, "buy_high": price,
                    "support": price * 0.9, "resistance": price * 1.2,
                    "ma20": price * 0.97, "trigger": "回踩企稳",
                    "position_hint": hint}}

CANDS = [_cand("600519", 90, 1450.0, "白酒"), _cand("000858", 85, 130.0, "白酒"),
         _cand("300750", 80, 250.0, "电池"), _cand("600036", 75, 35.0, "银行"),
         _cand("601318", 70, 50.0, "保险"), _cand("000001", 65, 12.0, "银行")]

def test_balanced_allocation_respects_caps():
    a = allocate(CANDS, 100000, "balanced", CFG)
    prof = CFG["advisor"]["risk_profiles"]["balanced"]
    total = sum(p["amount"] for p in a["picks"])
    assert a["cash_reserve"] >= prof["min_cash"] * 100000 - 1
    assert all(p["amount"] <= prof["max_pos"] * 100000 + 1 for p in a["picks"])
    by_ind = {}
    for p in a["picks"]:
        ind = next(c["industry"] for c in CANDS if c["code"] == p["code"])
        by_ind[ind] = by_ind.get(ind, 0) + p["amount"]
    assert all(v <= prof["max_industry"] * 100000 + 1 for v in by_ind.values())
    assert len(a["picks"]) <= prof["n_picks"]

def test_a_share_lots_rounded_and_unaffordable_dropped():
    a = allocate(CANDS, 30000, "conservative", CFG)   # 3万本金买不起茅台一手
    codes = [p["code"] for p in a["picks"]]
    assert "600519" not in codes                      # 1450×100 > 10%×30000
    assert all(p["shares"] % 100 == 0 for p in a["picks"])

def test_wait_hint_excluded():
    cands = [_cand("600000", 95, 10.0, "银行", hint="观望")] + CANDS[3:]
    a = allocate(cands, 100000, "balanced", CFG)
    assert "600000" not in [p["code"] for p in a["picks"]]

def test_batches_split_60_40():
    a = allocate(CANDS, 100000, "balanced", CFG)
    p = a["picks"][0]
    assert abs(p["first_batch"] + p["add_batch"] - p["amount"]) < 1
    assert p["first_batch"] > p["add_batch"]

def test_prompt_mentions_disclaimer_inputs():
    a = allocate(CANDS, 100000, "balanced", CFG)
    prompt = build_advisor_prompt(a, "a")
    assert "止损" in prompt and "风险" in prompt
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests_sgod/test_advisor.py -v`
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# portfolio_advisor/allocate.py
# 组合建议纯计算：排序→逐只装入(仓位/行业/现金约束)→A股一手取整。
from __future__ import annotations

def _rank_key(c):
    h = c.get("health_score")
    return c["score"] * ((h / 100) if h is not None else 0.8)

def allocate(candidates, capital, profile, cfg) -> dict:
    prof = cfg["advisor"]["risk_profiles"][profile]
    max_pos = prof["max_pos"] * capital
    max_ind = prof["max_industry"] * capital
    invest_budget = capital * (1 - prof["min_cash"])
    pool = [c for c in candidates
            if c.get("buy") and c["buy"].get("position_hint") != "观望"
            and c.get("price")]
    pool.sort(key=_rank_key, reverse=True)
    picks, by_ind, used = [], {}, 0.0
    for c in pool:
        if len(picks) >= prof["n_picks"] or used >= invest_budget - 1:
            break
        ind = c.get("industry") or "未知"
        room = min(max_pos, invest_budget - used, max_ind - by_ind.get(ind, 0.0))
        if room <= 0:
            continue
        if c["market"] == "a":
            lots = int(room // (c["price"] * 100))
            if lots < 1:
                continue                      # 买不起一手 → 顺位递补
            shares, amount = lots * 100, lots * 100 * c["price"]
        else:
            shares, amount = None, round(room, 2)
        picks.append({"code": c["code"], "name": c.get("name"),
                      "amount": round(amount, 2),
                      "weight": round(amount / capital * 100, 1),
                      "shares": shares,
                      "first_batch": round(amount * 0.6, 2),
                      "add_batch": round(amount * 0.4, 2),
                      "buy": c["buy"]})
        by_ind[ind] = by_ind.get(ind, 0.0) + amount
        used += amount
    return {"picks": picks, "cash_reserve": round(capital - used, 2),
            "cash_pct": round((capital - used) / capital * 100, 1)}
```

```python
# portfolio_advisor/report.py
from __future__ import annotations
import json
from sgod.llm import chat

def build_advisor_prompt(alloc, market):
    mkt = "A股" if market == "a" else "美股"
    return (f"{mkt}今日建议组合：{json.dumps(alloc, ensure_ascii=False)}\n"
            "请用200字内说明：1) 组合逻辑（为何这样分散与配比）；"
            "2) 主要风险；3) 止损与调仓条件（跌破支撑位/基本面恶化等）。"
            "语气克制专业，明确这是研究参考非投资建议。")

def advisor_report(alloc, market):
    if not alloc.get("picks"):
        return None
    return chat(build_advisor_prompt(alloc, market))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests_sgod/test_advisor.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add portfolio_advisor/ tests_sgod/test_advisor.py
git commit -m "feat(sgod): 投资策略建议(风险偏好/行业分散/一手取整/分批建仓)"
```

---

### Task 13: 企业微信推送 + HTML 日报 `sgod/wecom.py` + `sgod/html_report.py`

**Files:**
- Create: `sgod/wecom.py`
- Create: `sgod/html_report.py`
- Test: `tests_sgod/test_output.py`

**Interfaces:**
- Produces（wecom.py）: `build_daily_markdown(market, day, top, alloc, advisor_text, intel, web_url) -> str`（纯函数，≤4000 字节企业微信 markdown 限制，超长自动截断行业情报节）；`send_wecom(markdown: str) -> bool`（POST `SGOD_WECOM_WEBHOOK`，`{"msgtype": "markdown", "markdown": {"content": ...}}`，失败 False 不抛错）
- Produces（html_report.py）: `write_html_report(out_dir, market, day, top, finance_map, alloc, advisor_text, intel) -> Path` — 单文件自包含 HTML（内联 CSS，含完整 Top20 表、每只财务三卡与分析/展望、策略建议表、行业情报），写到 `{out_dir}/{day}-{market}.html` 并刷新 `{out_dir}/index.html`（近 30 天列表链接）
- Markdown 与 HTML 均以免责声明结尾（Global Constraints 的固定文案）

- [ ] **Step 1: 写失败测试**

```python
# tests_sgod/test_output.py
from sgod.wecom import build_daily_markdown
from sgod.html_report import write_html_report

TOP = [{"code": "600519", "name": "贵州茅台", "score": 90.0, "tags": [],
        "price": 1450.0, "industry": "白酒", "health_score": 85.0,
        "buy": {"buy_low": 1380.0, "buy_high": 1460.0, "support": 1350.0,
                "resistance": 1600.0, "ma20": 1400.0,
                "trigger": "回踩企稳", "position_hint": "标准"}}]
ALLOC = {"picks": [{"code": "600519", "name": "贵州茅台", "amount": 14500.0,
          "weight": 14.5, "shares": 100, "first_batch": 8700.0,
          "add_batch": 5800.0, "buy": TOP[0]["buy"]}],
         "cash_reserve": 85500.0, "cash_pct": 85.5}
INTEL = {"白酒": {"stocks": ["600519"], "news": ["标题"], "assessment": "中性：短期无催化"}}

def test_markdown_contains_key_sections_and_disclaimer():
    md = build_daily_markdown("a", "2026-07-29", TOP, ALLOC, "组合说明",
                              INTEL, "https://stock.cxodex.com")
    assert "贵州茅台" in md and "1380.0" in md
    assert "不构成投资建议" in md
    assert len(md.encode("utf-8")) <= 4000

def test_markdown_truncates_when_oversized():
    intel = {f"行业{i}": {"stocks": ["600519"], "news": ["x" * 50] * 8,
             "assessment": "中性：" + "很长的评估" * 30} for i in range(20)}
    md = build_daily_markdown("a", "2026-07-29", TOP * 5, ALLOC, "说明" * 100,
                              intel, "https://stock.cxodex.com")
    assert len(md.encode("utf-8")) <= 4000

def test_html_report_written_with_index(tmp_path):
    fmap = {"600519": {"cards": {"peer": {"gross_margin": 91.0}, "mgmt": {},
            "risk": {}}, "health": {"score": 85.0, "coverage": 1.0, "flags": []},
            "analysis_text": "分析", "outlook_text": "展望"}}
    p = write_html_report(tmp_path, "a", "2026-07-29", TOP, fmap, ALLOC,
                          "组合说明", INTEL)
    assert p.exists() and (tmp_path / "index.html").exists()
    html = p.read_text(encoding="utf-8")
    assert "贵州茅台" in html and "展望" in html and "不构成投资建议" in html
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests_sgod/test_output.py -v`
Expected: FAIL

- [ ] **Step 3: 实现（wecom 组装 + 截断策略：先砍情报→再砍策略文→保 Top5 表；html 用 f-string 模板，无第三方依赖）**

```python
# sgod/wecom.py
from __future__ import annotations
import os
import requests

DISCLAIMER = "本报告由 AI 生成，仅供研究参考，不构成投资建议，据此操作风险自负"
_LIMIT = 4000

def _top5_lines(top):
    lines = []
    for r in top[:5]:
        b = r.get("buy") or {}
        tag = f"[{'/'.join(r['tags'])}]" if r.get("tags") else ""
        h = r.get("health_score")
        lines.append(
            f"**{r['name']}({r['code']})**{tag} 分{r['score']}"
            f"{f' 财务{h}' if h is not None else ''}\n"
            f"> 买点 {b.get('buy_low')}~{b.get('buy_high')} {b.get('position_hint', '')}"
            f"｜{b.get('trigger', '')}")
    return lines

def build_daily_markdown(market, day, top, alloc, advisor_text, intel, web_url):
    mkt = "A股" if market == "a" else "美股"
    head = f"# 📈 Cxodex 选股神器 · {mkt} {day}\n共筛出 {len(top)} 只新面孔，Top5：\n"
    picks = "\n".join(_top5_lines(top))
    strat = ""
    if alloc and alloc.get("picks"):
        rows = "、".join(f"{p['name']} {p['weight']}%" for p in alloc["picks"])
        strat = (f"\n## 今日策略建议\n{rows}｜现金 {alloc['cash_pct']}%\n"
                 + (advisor_text or ""))
    intel_txt = "\n## 行业情报\n" + "\n".join(
        f"- **{ind}**：{v['assessment']}" for ind, v in (intel or {}).items()
        if v.get("assessment"))
    tail = f"\n\n[完整报告]({web_url})\n> {DISCLAIMER}"
    for parts in ((head, picks, strat, intel_txt),   # 全量
                  (head, picks, strat, ""),          # 砍情报
                  (head, picks, "", "")):            # 砍策略
        md = "".join(parts) + tail
        if len(md.encode("utf-8")) <= _LIMIT:
            return md
    return (head + tail)[: _LIMIT]

def send_wecom(markdown: str) -> bool:
    url = os.getenv("SGOD_WECOM_WEBHOOK")
    if not url:
        return False
    try:
        resp = requests.post(url, json={"msgtype": "markdown",
                                        "markdown": {"content": markdown}},
                             timeout=15)
        return resp.status_code == 200 and resp.json().get("errcode") == 0
    except requests.RequestException:
        return False
```

```python
# sgod/html_report.py
from __future__ import annotations
import html as _html
from pathlib import Path
from .wecom import DISCLAIMER

_CSS = ("body{font-family:system-ui;max-width:1080px;margin:24px auto;padding:0 16px;"
        "background:#0f1115;color:#e6e6e6}table{border-collapse:collapse;width:100%;"
        "margin:12px 0}td,th{border:1px solid #333;padding:6px 10px;font-size:14px}"
        "th{background:#1a1d24}h1,h2{color:#e8c66a}.card{background:#1a1d24;"
        "border-radius:10px;padding:14px;margin:10px 0}.flag{color:#ff7a6b}"
        ".dis{color:#888;font-size:12px;margin-top:28px}")

def _esc(v):
    return _html.escape(str(v)) if v is not None else "—"

def _fin_block(code, fmap):
    f = (fmap or {}).get(code)
    if not f:
        return "<p>财务数据不足</p>"
    h = f["health"]
    flags = "".join(f'<div class="flag">⚠ {_esc(x)}</div>' for x in h.get("flags", []))
    return (f'<p>财务健康分：<b>{_esc(h.get("score"))}</b>'
            f'（覆盖率 {_esc(h.get("coverage"))}）</p>{flags}'
            f'<p>{_esc(f.get("analysis_text") or "AI 分析暂缺")}</p>'
            f'<p><i>{_esc(f.get("outlook_text") or "")}</i></p>')

def write_html_report(out_dir, market, day, top, finance_map, alloc,
                      advisor_text, intel) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mkt = "A股" if market == "a" else "美股"
    rows = ""
    for r in top:
        b = r.get("buy") or {}
        rows += (f"<tr><td>{_esc(r['code'])}</td><td>{_esc(r['name'])}"
                 f"{'（' + '/'.join(r['tags']) + '）' if r.get('tags') else ''}</td>"
                 f"<td>{_esc(r['score'])}</td><td>{_esc(r.get('industry'))}</td>"
                 f"<td>{_esc(b.get('buy_low'))}~{_esc(b.get('buy_high'))}</td>"
                 f"<td>{_esc(b.get('position_hint'))}</td></tr>")
    cards = "".join(f'<div class="card"><h3>{_esc(r["name"])}（{_esc(r["code"])}）</h3>'
                    f'{_fin_block(r["code"], finance_map)}</div>' for r in top)
    strat = ""
    if alloc and alloc.get("picks"):
        srows = "".join(f"<tr><td>{_esc(p['name'])}</td><td>{p['amount']}</td>"
                        f"<td>{p['weight']}%</td><td>{_esc(p['shares'])}</td>"
                        f"<td>{p['first_batch']} / {p['add_batch']}</td></tr>"
                        for p in alloc["picks"])
        strat = (f"<h2>今日策略建议</h2><table><tr><th>股票</th><th>金额</th>"
                 f"<th>占比</th><th>股数</th><th>首建/加仓</th></tr>{srows}</table>"
                 f"<p>现金保留：{alloc['cash_pct']}%</p><p>{_esc(advisor_text or '')}</p>")
    intel_html = "".join(f'<div class="card"><b>{_esc(ind)}</b>'
                         f"<p>{_esc(v.get('assessment') or '暂缺')}</p></div>"
                         for ind, v in (intel or {}).items())
    page = (f"<!doctype html><meta charset='utf-8'><title>{mkt} {day} 选股日报</title>"
            f"<style>{_CSS}</style><h1>Cxodex 选股神器 · {mkt} {day}</h1>"
            f"<h2>今日新面孔 Top{len(top)}</h2><table><tr><th>代码</th><th>名称</th>"
            f"<th>综合分</th><th>行业</th><th>买入区间</th><th>仓位提示</th></tr>"
            f"{rows}</table>{strat}<h2>行业情报</h2>{intel_html}"
            f"<h2>个股财务分析（IMDS）</h2>{cards}"
            f"<p class='dis'>{DISCLAIMER}</p>")
    path = out / f"{day}-{market}.html"
    path.write_text(page, encoding="utf-8")
    items = sorted(out.glob("*-*.html"), reverse=True)[:60]
    idx = "".join(f'<li><a href="{p.name}">{p.stem}</a></li>'
                  for p in items if p.name != "index.html")
    (out / "index.html").write_text(
        f"<!doctype html><meta charset='utf-8'><title>选股日报</title>"
        f"<style>{_CSS}</style><h1>Cxodex 选股神器 · 历史日报</h1><ul>{idx}</ul>",
        encoding="utf-8")
    return path
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests_sgod/test_output.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add sgod/wecom.py sgod/html_report.py tests_sgod/test_output.py
git commit -m "feat(sgod): 企业微信markdown(4000B截断)+自包含HTML日报"
```

---

### Task 14: 总编排器 `run_daily.py`

**Files:**
- Create: `run_daily.py`（仓库根，与 main.py 平级）
- Test: `tests_sgod/test_run_daily.py`

**Interfaces:**
- Consumes: 前面全部模块
- Produces: CLI `python run_daily.py --market a|us [--limit N] [--dry-run] [--no-deep] [--no-notify]`；核心函数 `run_session(market, cfg, limit=None, deep=True, notify=True, out_dir=None) -> dict`（返回 `{"top": [...], "finance_map": {...}, "alloc": {...}, "intel": {...}, "html_path": str, "pushed": bool}`）
- 流程：①`run_screener` → ②`--no-deep` 之外以子进程 `python main.py --stocks <20码逗号> --no-notify --force-run` 复用原深度流水线（超时 30 分钟；失败仅告警不中断，Web 端少深度报告但日报照出）→ ③逐只 `fetch_industry`+`fetch_series`+`finance_report`（把 `health["score"]` 写回候选的 `health_score`）→ ④`gather_intel` → ⑤`allocate`+`advisor_report`（capital 取 env `SGOD_CAPITAL`/`SGOD_RISK_PROFILE`，缺省用 cfg）→ ⑥`write_html_report` 到 `data/sgod/reports/` → ⑦`build_daily_markdown`+`send_wecom` → ⑧`history.record`（dry-run 跳过 ⑦⑧）
- A股股票码传给 main.py 保持 6 位数字；美股直接 ticker（上游 `canonical_stock_code` 兼容两者）
- 数据源整场失败（SnapshotError）：推送「⚠ 选股神器数据源故障」告警到企业微信后退出码 1

- [ ] **Step 1: 写失败测试**

```python
# tests_sgod/test_run_daily.py
import run_daily
from screener.filters import load_sgod_config

CFG = load_sgod_config()

TOP = [{"code": "600519", "name": "贵州茅台", "market": "a", "score": 90.0,
        "price": 1450.0, "tags": [], "buy": {"buy_low": 1380.0,
        "buy_high": 1460.0, "support": 1350.0, "resistance": 1600.0,
        "ma20": 1400.0, "trigger": "回踩企稳", "position_hint": "标准"}}]

def test_run_session_wires_everything(tmp_path, monkeypatch):
    monkeypatch.setattr(run_daily, "run_screener", lambda *a, **k: [dict(r) for r in TOP])
    monkeypatch.setattr(run_daily, "_run_deep_pipeline", lambda codes: True)
    monkeypatch.setattr(run_daily, "fetch_industry", lambda c, m: "白酒")
    monkeypatch.setattr(run_daily, "fetch_series", lambda c, m: [])
    monkeypatch.setattr(run_daily, "finance_report", lambda *a, **k:
                        {"cards": {}, "health": {"score": 85.0, "coverage": 1.0,
                         "flags": []}, "analysis_text": "分析", "outlook_text": "展望"})
    monkeypatch.setattr(run_daily, "gather_intel", lambda cands, m:
                        {"白酒": {"stocks": ["600519"], "news": [], "assessment": "中性：观察"}})
    monkeypatch.setattr(run_daily, "advisor_report", lambda *a, **k: "组合说明")
    sent = {}
    monkeypatch.setattr(run_daily, "send_wecom", lambda md: sent.setdefault("md", md) or True)
    monkeypatch.setattr(run_daily, "DB_PATH", tmp_path / "h.db")
    result = run_daily.run_session("a", CFG, deep=True, notify=True,
                                   out_dir=tmp_path / "reports")
    assert result["pushed"] is True
    assert "贵州茅台" in sent["md"]
    assert result["top"][0]["health_score"] == 85.0     # 财务分写回候选
    assert (tmp_path / "reports").exists()

def test_dry_run_skips_push_and_history(tmp_path, monkeypatch):
    monkeypatch.setattr(run_daily, "run_screener", lambda *a, **k: [dict(r) for r in TOP])
    monkeypatch.setattr(run_daily, "fetch_industry", lambda c, m: None)
    monkeypatch.setattr(run_daily, "fetch_series", lambda c, m: [])
    monkeypatch.setattr(run_daily, "finance_report", lambda *a, **k:
                        {"cards": {}, "health": {"score": None, "coverage": 0.0,
                         "flags": []}, "analysis_text": None, "outlook_text": None})
    monkeypatch.setattr(run_daily, "gather_intel", lambda *a, **k: {})
    monkeypatch.setattr(run_daily, "advisor_report", lambda *a, **k: None)
    called = []
    monkeypatch.setattr(run_daily, "send_wecom", lambda md: called.append(md))
    monkeypatch.setattr(run_daily, "DB_PATH", tmp_path / "h.db")
    result = run_daily.run_session("a", CFG, deep=False, notify=False,
                                   out_dir=tmp_path / "reports")
    assert called == [] and result["pushed"] is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests_sgod/test_run_daily.py -v`
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# run_daily.py — Cxodex 选股神器总编排器。原 main.py 流水线零修改，以子进程复用。
from __future__ import annotations
import argparse, os, subprocess, sys
from datetime import date
from pathlib import Path

from screener.run import run_screener, DB_PATH
from screener.filters import load_sgod_config
from screener.history import RecommendHistory
from imds_finance.fetch import fetch_series, fetch_industry, fetch_peer_median
from imds_finance.report import finance_report
from industry_intel.run import gather_intel
from portfolio_advisor.allocate import allocate
from portfolio_advisor.report import advisor_report
from sgod.wecom import build_daily_markdown, send_wecom
from sgod.html_report import write_html_report

REPORT_DIR = Path(__file__).resolve().parent / "data" / "sgod" / "reports"

def _run_deep_pipeline(codes) -> bool:
    """子进程复用上游深度分析；失败不中断日报。"""
    cmd = [sys.executable, "main.py", "--stocks", ",".join(codes),
           "--no-notify", "--force-run"]
    try:
        r = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parent),
                           timeout=1800, capture_output=True)
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False

def run_session(market, cfg, limit=None, deep=True, notify=True, out_dir=None):
    history = RecommendHistory(DB_PATH)
    top = run_screener(market, cfg, history, top_n=limit)
    if deep and top:
        _run_deep_pipeline([r["code"] for r in top])
    finance_map = {}
    for r in top:
        r["industry"] = fetch_industry(r["code"], market)
        series = fetch_series(r["code"], market)
        rep = finance_report(r["code"], r["name"], market, series,
                             industry=r.get("industry"))
        finance_map[r["code"]] = rep
        r["health_score"] = rep["health"]["score"]
    intel = gather_intel(top, market)
    capital = float(os.getenv("SGOD_CAPITAL", cfg["advisor"]["capital_base"]))
    profile = os.getenv("SGOD_RISK_PROFILE", "balanced")
    alloc = allocate(top, capital, profile, cfg)
    advisor_text = advisor_report(alloc, market)
    day = date.today().isoformat()
    html_path = write_html_report(out_dir or REPORT_DIR, market, day, top,
                                  finance_map, alloc, advisor_text, intel)
    pushed = False
    if notify:
        web_url = os.getenv("SGOD_WEB_URL", "https://stock.cxodex.com") \
            + f"/daily/{html_path.name}"
        md = build_daily_markdown(market, day, top, alloc, advisor_text,
                                  intel, web_url)
        pushed = bool(send_wecom(md))
        history.record(market, [r["code"] for r in top], day)
    return {"top": top, "finance_map": finance_map, "alloc": alloc,
            "intel": intel, "html_path": str(html_path), "pushed": pushed}

def main():
    p = argparse.ArgumentParser(description="Cxodex 选股神器 · 每日场次")
    p.add_argument("--market", choices=("a", "us"), required=True)
    p.add_argument("--limit", type=int, default=None, help="候选数上限(调试)")
    p.add_argument("--dry-run", action="store_true", help="不推送不写历史")
    p.add_argument("--no-deep", action="store_true", help="跳过深度分析子进程")
    p.add_argument("--no-notify", action="store_true")
    args = p.parse_args()
    cfg = load_sgod_config()
    try:
        result = run_session(args.market, cfg, limit=args.limit,
                             deep=not args.no_deep,
                             notify=not (args.dry_run or args.no_notify))
    except Exception as e:
        send_wecom(f"⚠ 选股神器 {args.market} 场次失败：{e}")
        raise SystemExit(1)
    print(f"完成：Top{len(result['top'])}，日报 {result['html_path']}，"
          f"推送 {'成功' if result['pushed'] else '未推送'}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests_sgod/test_run_daily.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 全量回归**

Run: `python -m pytest tests_sgod/ -v`
Expected: 全部 PASS（约 28 个）

- [ ] **Step 6: Commit**

```bash
git add run_daily.py tests_sgod/test_run_daily.py
git commit -m "feat(sgod): 总编排器——初筛→深度→财务→情报→策略→日报→推送"
```

---

### Task 15: 本机端到端冒烟 + README 补充

**Files:**
- Modify: 无上游文件；Create: `docs/sgod-README.md`

**Interfaces:**
- Consumes: 全部模块；需要本机 `.env`（GLM_API_KEY 可暂缺——降级路径也是验证点）

- [ ] **Step 1: 装依赖并跑纯初筛冒烟（不调 LLM 不推送）**

Run: `pip install -r requirements.txt pyyaml && python run_daily.py --market a --limit 3 --dry-run --no-deep`
Expected: 打印「完成：Top3，日报 data/sgod/reports/….html，推送 未推送」；打开 HTML 目视检查表格/财务卡/免责声明

- [ ] **Step 2: 美股场次冒烟**

Run: `python run_daily.py --market us --limit 3 --dry-run --no-deep`
Expected: 同上（美股快照较慢属正常；若东财美股接口超时，记录到 sgod-README 已知问题）

- [ ] **Step 3: 写 `docs/sgod-README.md`**

内容（完整写入，不是占位）：功能一览（5能力对照）、CLI 用法（`run_daily.py`/`screener.run` 全参数）、环境变量表（`GLM_API_KEY`/`GLM_BASE_URL`/`GLM_MODEL`/`SGOD_WECOM_WEBHOOK`/`TAVILY_API_KEY`/`SGOD_CAPITAL`/`SGOD_RISK_PROFILE`/`SGOD_WEB_URL`）、config/sgod.yaml 参数说明、数据流图（文字版）、已知限制（美股无同行中位数、快照限流、LLM 降级语义）、免责声明。

- [ ] **Step 4: Commit**

```bash
git add docs/sgod-README.md
git commit -m "docs(sgod): 使用手册(CLI/环境变量/参数/已知限制)"
```

---

### Task 16: cxodex 门户卡片

**Files:**
- Modify: `D:\Projects\Cxodex\cxodex-portal\index.html`（找到应用卡片 JS 数组，`企业财务分析` 条目之后插入）

**Interfaces:**
- Consumes: 门户现有卡片数组结构 `{ icon, name, desc, url }`

- [ ] **Step 1: 插入卡片**

在 `{ icon:"📊", name:"企业财务分析", ... }` 之后插入：

```js
  { icon:"📈", name:"Cxodex 选股神器", desc:"A股+美股每日全市场自动选股：IMDS 财务分析与展望、最佳买点、投资策略建议、行业情报。", url:"https://stock.cxodex.com" },
```

- [ ] **Step 2: 本地目视验证**

Run: 在浏览器打开 `D:\Projects\Cxodex\cxodex-portal\index.html`
Expected: 新卡片出现且样式与其他卡片一致、点击跳 stock.cxodex.com

- [ ] **Step 3: Commit（门户是独立 git 仓库则单独提交；无仓库则记录到部署清单待服务器同步）**

```bash
cd /d/Projects/Cxodex/cxodex-portal && git add index.html && git commit -m "feat: 新增 Cxodex 选股神器卡片 → stock.cxodex.com" || echo "非git目录，随部署手册同步"
```

---

### Task 17: 部署物 `deploy/sgod/`

**Files:**
- Create: `deploy/sgod/env.template`
- Create: `deploy/sgod/nginx-stock.conf`
- Create: `deploy/sgod/crontab.txt`
- Create: `deploy/sgod/DEPLOY.md`

**Interfaces:**
- Consumes: 全部；产出可复制粘贴执行的部署手册

- [ ] **Step 1: 写 `deploy/sgod/env.template`**

```bash
# /opt/stock-analysis/.env —— 选股神器环境变量（真实值 SSH 上填，勿入 git）
GLM_API_KEY=
GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
GLM_MODEL=glm-5.2
SGOD_WECOM_WEBHOOK=
TAVILY_API_KEY=
SGOD_CAPITAL=100000
SGOD_RISK_PROFILE=balanced
SGOD_WEB_URL=https://stock.cxodex.com
# —— 以下供上游深度流水线(main.py 子进程)使用，同一 GLM Key 走 OpenAI 兼容 ——
OPENAI_API_KEY=${GLM_API_KEY}
OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
OPENAI_MODEL=glm-5.2
WEBUI_PORT=3024
WEBUI_HOST=127.0.0.1
```

- [ ] **Step 2: 写 `deploy/sgod/nginx-stock.conf`**

```nginx
# /etc/nginx/sites-available/stock.cxodex.com（certbot 会自动补 443 段）
server {
    listen 80;
    server_name stock.cxodex.com;
    # 每日静态日报（run_daily.py 产物）
    location /daily/ {
        alias /opt/stock-analysis/data/sgod/reports/;
        index index.html;
        charset utf-8;
    }
    # 原项目 Web 工作台
    location / {
        proxy_pass http://127.0.0.1:3024;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

- [ ] **Step 3: 写 `deploy/sgod/crontab.txt`**

```cron
# 服务器为 UTC 时区（腾讯云 HK 默认）——北京时间 = UTC+8
# A股场次：北京时间周一至五 17:30 → UTC 09:30
30 9 * * 1-5 cd /opt/stock-analysis && /opt/stock-analysis/venv/bin/python run_daily.py --market a >> logs/sgod-a.log 2>&1
# 美股场次：北京时间周二至六 07:30 → UTC 前一日 23:30（周一至五）
30 23 * * 1-5 cd /opt/stock-analysis && /opt/stock-analysis/venv/bin/python run_daily.py --market us >> logs/sgod-us.log 2>&1
# 非交易日：run_daily 内部不做日历判断，依赖上游 --force-run 语义；
# 快照为空/节假日接口无数据时当日自然产出空报告——首版接受，观察一周后再决定是否加交易日历
```

- [ ] **Step 4: 写 `deploy/sgod/DEPLOY.md`（完整命令清单）**

内容必须包含以下全部步骤的可粘贴命令：
1. 前置：用户在域名控制台加 A 记录 `stock` → `43.160.214.195`；`ping stock.cxodex.com` 验证
2. `git clone https://github.com/Alfred2030/daily_stock_analysis.git /opt/stock-analysis && cd /opt/stock-analysis && python3 -m venv venv && venv/bin/pip install -r requirements.txt pyyaml`
3. `cp deploy/sgod/env.template .env && vim .env`（填 GLM Key/企业微信 webhook/Tavily Key）
4. 冒烟：`venv/bin/python run_daily.py --market a --limit 3 --dry-run --no-deep`
5. Web 工作台：`pm2 start "venv/bin/python main.py --webui-only --port 3024" --name stock && pm2 save`
6. nginx：`cp deploy/sgod/nginx-stock.conf /etc/nginx/sites-available/stock.cxodex.com && ln -s ../sites-available/stock.cxodex.com /etc/nginx/sites-enabled/ && nginx -t && systemctl reload nginx && certbot --nginx -d stock.cxodex.com`
7. cron：`crontab -e` 追加 `deploy/sgod/crontab.txt` 两行；`mkdir -p logs`
8. 首推验证：`venv/bin/python run_daily.py --market a --limit 5` 看企业微信是否收到
9. 门户卡片：把更新后的 `cxodex-portal/index.html` 同步到服务器 `/var/www/` 对应目录（沿用门户现行部署方式）
10. 账本回写：`D:\Alfred Vault\30-业务\CXODEX-运维账本\` 新增 `stock-analysis.md`（域名/端口3024/PM2名stock/cron两条/日志路径），索引加一行

- [ ] **Step 5: Commit**

```bash
git add deploy/sgod/
git commit -m "feat(sgod): 部署物——env模板/nginx/cron/部署手册"
```

---

### Task 18: 推送 GitHub + 服务器部署执行

**Files:** 无新文件（执行 Task 17 的手册）

- [ ] **Step 1: 推送 fork**

```bash
cd "D:/Daily stock/daily_stock_analysis" && git push origin main
```

- [ ] **Step 2: 确认 DNS 已生效（用户加记录后）**

Run: `nslookup stock.cxodex.com`
Expected: 解析到 43.160.214.195；未生效则暂停部署等待用户

- [ ] **Step 3: 按 DEPLOY.md 在服务器执行 2-8 步**

SSH 到 43.160.214.195 逐步执行；每步失败即停，排查后再继续。`.env` 的真实 Key 由用户 SSH 填写。

- [ ] **Step 4: 验收清单**

- `https://stock.cxodex.com` 打开 Web 工作台（HTTPS 正常）
- `https://stock.cxodex.com/daily/` 能看到日报列表
- 企业微信收到测试推送（含 Top5/策略建议/免责声明）
- `pm2 ls` 中 `stock` online；`crontab -l` 两条任务在
- 门户 `app.cxodex.com` 出现「Cxodex 选股神器」卡片
- 连续观察 3 个交易日推送正常后视为交付完成

- [ ] **Step 5: 账本回写（完成后）**

在 `D:\Alfred Vault\30-业务\CXODEX-运维账本\stock-analysis.md` 记录：域名、端口、PM2 进程名、cron、日志路径、.env 变量清单（不含值）、已知限制；`_运维账本索引.md` 加一行。

---

## Self-Review 记录

- **Spec 覆盖**：功能1→Task 1-6（含新股次新标签）；功能2→Task 7-10（分析+展望两节）；功能3→Task 5（量化）+上游深度报告（子进程保留）；功能4→Task 12；功能5→Task 11；门户卡片→Task 16；部署/推送/域名→Task 13、17、18；原功能不变→零上游文件修改（Task 14 子进程复用）。
- **占位符扫描**：Task 15/17 的文档步骤给出了必含内容清单（文档性任务），其余任务全部带完整代码。
- **类型一致性**：`buy_zone` 返回字段与 Task 12/13 消费字段核对一致（`buy_low/buy_high/position_hint/trigger/support/resistance/ma20`）；`health_score` 返回 `{"score","coverage","flags"}` 与 Task 10/13/14 一致；`run_screener` 签名在 Task 6/14 一致；`_piecewise` 从 `screener/scoring.py` 导入复用于 `imds_finance/scoring.py`。
- **已知妥协**（首版接受，文档记录）：美股无同行中位数；`fetch_peer_median` 首版只有 PE/PB 中位数（毛利率/ROE 需逐股拉财报，成本高）；非交易日依赖快照自然为空，未接交易日历。
