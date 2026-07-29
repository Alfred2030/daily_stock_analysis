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
