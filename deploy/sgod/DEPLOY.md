# 选股神器（SGOD）部署手册 —— 腾讯云 HK Lighthouse

目标服务器：`43.160.214.195`（腾讯云香港 Lighthouse，Ubuntu，已装 nginx / certbot / pm2 / python3，同机跑着其他 cxodex 应用，端口 3000-3023 已被占用，**本应用固定用 3024**）。

以下命令均假设 **SSH 以 root 身份登录服务器执行**（`ssh root@43.160.214.195`），除非另有说明。命令按顺序执行；标 `【本机】` 的步骤在你的工作站（Windows）执行，其余在服务器执行。仓库当前处于 `feature/sgod` 分支，**尚未合并到 main**，因此下面 clone 后需要显式 `git checkout feature/sgod`；合并到 main 后可去掉该步。

---

## 1. 域名解析（【本机/域名控制台】）

在域名服务商控制台给 `cxodex.com` 加一条 A 记录：

| 类型 | 主机记录 | 记录值 |
|---|---|---|
| A | `stock` | `43.160.214.195` |

添加后等待 DNS 生效（通常几分钟到一小时），验证：

```bash
ping stock.cxodex.com
```

看到解析出 `43.160.214.195` 即可继续（`ping` 本身可能被服务器防火墙拦回包无响应，只要地址解析对即可，不必强求 ping 通）。

---

## 2. 拉代码 + 建虚拟环境 + 装依赖（服务器）

```bash
git clone https://github.com/Alfred2030/daily_stock_analysis.git /opt/stock-analysis
cd /opt/stock-analysis
git checkout feature/sgod   # 尚未合并 main 前必须切这个分支；合并后可省略此行
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt pyyaml
```

`requirements.txt` 里有一些依赖（如 `futu-api`、`longbridge`、`tickflow`）体积较大或需要构建工具，**若上面这条在服务器上失败**（编译报错、拉取超时等），先尝试补装系统构建工具再重跑一次：

```bash
apt-get update && apt-get install -y build-essential python3-dev
venv/bin/pip install -r requirements.txt pyyaml
```

**如果仍然失败**（例如某个数据源 SDK 在当前 Python/系统版本上没有可用 wheel），退而求其次，只装选股神器（screener-only 模式）实际用到的最小依赖集，跳过 `main.py` 深度分析子进程需要的重依赖：

```bash
venv/bin/pip install akshare pyyaml requests pandas python-dotenv tenacity sqlalchemy
```

注意：走最小依赖集时，`run_daily.py` 不加 `--no-deep` 会因缺依赖调用 `main.py` 子进程失败——此时**部署与 cron 都必须固定加 `--no-deep`**（见第 4、7 步），只跑「初筛 + 财务/情报/策略」而不跑上游个股深度分析。

---

## 3. 配置环境变量（服务器）

```bash
cp deploy/sgod/env.template .env
vim .env
```

需要手填的敏感值（**不要提交进 git**）：

- `GLM_API_KEY`：智谱 GLM API Key
- `SGOD_WECOM_WEBHOOK`：企业微信群机器人 Webhook 地址
- `TAVILY_API_KEY`：Tavily 搜索 API Key

其余变量（`GLM_BASE_URL`/`GLM_MODEL`/`SGOD_CAPITAL`/`SGOD_RISK_PROFILE`/`SGOD_WEB_URL`/`OPENAI_*`/`WEBUI_PORT`/`WEBUI_HOST`）模板里已给出可用默认值，一般无需改动。

---

## 4. 冒烟测试（服务器）

```bash
cd /opt/stock-analysis
venv/bin/python run_daily.py --market a --limit 3 --dry-run --no-deep
```

`--dry-run` 不推送、不写推荐历史，只跑一遍产出 HTML 日报，用于验证网络（东财快照接口）与依赖是否正常。若终端「零输出、退出码 1」，这是 `run_daily.py` 顶层 `SystemExit(1)` 设计使然（见 `docs/sgod-README.md` 第 2.1 节），改用下面这条看具体异常堆栈：

```bash
venv/bin/python -m screener.run --market a --dry-run --top 3
```

确认 A 股场次没问题后，同样跑一遍美股场次：

```bash
venv/bin/python run_daily.py --market us --limit 3 --dry-run --no-deep
```

---

## 5. 启动 Web 工作台（服务器，pm2）

```bash
cd /opt/stock-analysis
pm2 start "venv/bin/python main.py --webui-only --port 3024" --name stock
pm2 save
```

`pm2 save` 把当前进程列表写入 pm2 的开机自启清单，服务器重启后 `pm2 resurrect`（通常已配 systemd/pm2 startup）会自动拉起。

验证：

```bash
pm2 status stock
curl -sI http://127.0.0.1:3024/ | head -1
```

---

## 6. Nginx 反代 + HTTPS（服务器）

```bash
cd /opt/stock-analysis
cp deploy/sgod/nginx-stock.conf /etc/nginx/sites-available/stock.cxodex.com
ln -s ../sites-available/stock.cxodex.com /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
certbot --nginx -d stock.cxodex.com
```

`nginx -t` 若报错，先检查 `/etc/nginx/sites-enabled/` 里有没有同名 `server_name` 冲突（同机跑了其他 cxodex 应用）。`certbot --nginx` 会自动在 80 段基础上补 443 段并处理证书续期。

证书签发完成后验证：

```bash
curl -sI https://stock.cxodex.com/ | head -1
curl -sI https://stock.cxodex.com/daily/ | head -1
```

---

## 7. 配置定时任务（服务器）

```bash
mkdir -p /opt/stock-analysis/logs
crontab -e
```

在打开的编辑器里追加 `deploy/sgod/crontab.txt` 里的两行任务（不要覆盖服务器上已有的其他 crontab 条目）：

```cron
30 9 * * 1-5 cd /opt/stock-analysis && /opt/stock-analysis/venv/bin/python run_daily.py --market a >> logs/sgod-a.log 2>&1
30 23 * * 1-5 cd /opt/stock-analysis && /opt/stock-analysis/venv/bin/python run_daily.py --market us >> logs/sgod-us.log 2>&1
```

保存退出后确认已生效：

```bash
crontab -l
```

> 若第 2 步走的是「最小依赖集」降级安装，上面两行命令需要各自加上 `--no-deep`：
> `... run_daily.py --market a --no-deep >> logs/sgod-a.log 2>&1`

---

## 8. 首次真实推送验证（服务器）

```bash
cd /opt/stock-analysis
venv/bin/python run_daily.py --market a --limit 5
```

不加 `--dry-run`，会真实推送到企业微信群（`.env` 里 `SGOD_WECOM_WEBHOOK` 必须已填）并写入推荐历史。去对应企业微信群里确认收到日报消息；同时检查：

```bash
ls -la /opt/stock-analysis/data/sgod/reports/
tail -n 50 /opt/stock-analysis/logs/sgod-a.log
```

确认当天的 `<日期>-a.html` 已生成，且可通过 `https://stock.cxodex.com/daily/` 访问到。

---

## 9. 门户卡片同步（【本机】+ 服务器）

服务器上的门户静态目录具体子目录路径不完全确定（同机多个 cxodex 应用共用 `/var/www`），先在服务器上定位：

```bash
grep -rl "cxodex" /var/www --include=index.html | head
```

找到对应门户 `index.html` 路径后（下面用 `<portal-index-path>` 代指该完整路径），先备份：

```bash
cp <portal-index-path> <portal-index-path>.bak.$(date +%Y%m%d%H%M%S)
```

【本机】把已更新（加了「选股神器」卡片）的门户首页从工作站传到服务器覆盖对应文件（沿用门户现行部署方式，用 `scp`）：

```bash
scp "D:\Projects\Cxodex\cxodex-portal\index.html" root@43.160.214.195:<portal-index-path>
```

传完后浏览器访问门户首页，确认新卡片展示正常、点击能跳到 `https://stock.cxodex.com/`。若展示异常，用第一步的 `.bak` 文件回滚：

```bash
cp <portal-index-path>.bak.<时间戳> <portal-index-path>
```

---

## 10. 账本回写（【本机】）

部署全部完成、且第 8 步真实推送验证通过后，在工作站新增运维账本条目文件 `D:\Alfred Vault\30-业务\CXODEX-运维账本\stock-analysis.md`，至少包含以下信息（不要写任何密钥/密码明文）：

- 域名：`https://stock.cxodex.com`（80→443 由 certbot 自动跳转，`/daily/` 为静态日报目录，`/` 反代到 Web 工作台）
- 端口：`3024`（`WEBUI_PORT`/`WEBUI_HOST=127.0.0.1`，仅本机回环，经 nginx 对外）
- PM2 进程名：`stock`（`pm2 status stock` 查看，`pm2 restart stock` 重启，`pm2 logs stock` 看日志）
- 定时任务：两条见 `deploy/sgod/crontab.txt`（A股场次 UTC 09:30 = 北京 17:30；美股场次 UTC 23:30 = 北京次日 07:30）
- 日志路径：`/opt/stock-analysis/logs/sgod-a.log`、`/opt/stock-analysis/logs/sgod-us.log`
- 环境变量清单（**只列变量名，不列值**）：`GLM_API_KEY`、`GLM_BASE_URL`、`GLM_MODEL`、`SGOD_WECOM_WEBHOOK`、`TAVILY_API_KEY`、`SGOD_CAPITAL`、`SGOD_RISK_PROFILE`、`SGOD_WEB_URL`、`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`WEBUI_PORT`、`WEBUI_HOST`
- 已知限制：见 `docs/sgod-README.md` 第 6 节（东财快照限流/超时会中断当次场次、LLM/Tavily/WeCom 未配置时的降级行为、非交易日快照自然为空等）；若第 2 步走了「最小依赖集」降级安装，额外注明「screener-only 模式，`run_daily.py` 固定加 `--no-deep`，不跑 `main.py` 深度分析子进程」

写完后回到 `D:\Alfred Vault\30-业务\CXODEX-运维账本\_运维账本索引.md`，在合适位置（按现有条目风格，`- [[stock-analysis|选股神器]] — ...` 一行）追加一条索引，简述部署状态、域名、端口，方便日后 grep 命中。

---

## 附：已知限制速查

- 网络问题（东财 `eastmoney` 接口读超时）会导致 `screener.snapshot.SnapshotError`，整场次中断——本机开发环境已复现，服务器网络状况需以第 4/8 步的现场冒烟结果为准，不要凭本地经验假设服务器一定通畅。
- `run_daily.py` 顶层异常统一走 `SystemExit(1)`，终端零输出不代表脚本没跑，需要看 `logs/sgod-*.log` 或改用 `python -m screener.run` 排障。
- `GLM_API_KEY`/`TAVILY_API_KEY`/`SGOD_WECOM_WEBHOOK` 任一缺失只降级对应能力，不会导致整个流程崩溃（详见 `docs/sgod-README.md` 第 3 节环境变量表）。
