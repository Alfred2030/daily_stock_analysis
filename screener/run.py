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
