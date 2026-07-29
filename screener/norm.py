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
