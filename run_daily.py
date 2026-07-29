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
