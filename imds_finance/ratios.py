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
