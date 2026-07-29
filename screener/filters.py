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
        if market == "us":
            code = str(r.get("code") or "")
            if "." in code or "_" in code:      # 单位/权证等非普通股后缀
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
