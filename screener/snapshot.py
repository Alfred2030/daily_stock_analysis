# screener/snapshot.py
# 注：clist fallback 使用 push2delay 行情源（延迟 15 分钟）。
# 收盘后的日间批处理不受影响；单页硬上限 100 条，分页循环最多 150 页。
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

_CLIST_URL = "https://push2delay.eastmoney.com/api/qt/clist/get"
_CLIST_FIELDS = "f2,f3,f6,f8,f9,f10,f12,f13,f14,f20,f21,f23,f24,f115"
_FS = {"a": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23", "us": "m:105,m:106,m:107"}
_UT = "bd1d9ddb04089700cf9c27f6f7426281"

def _clist_page(market, pn, pz=100):
    """单页原始行；网络失败抛异常由调用方处理。"""
    import requests
    r = requests.get(_CLIST_URL, params={
        "pn": pn, "pz": pz, "po": 1, "np": 1, "fltt": 2, "invt": 2,
        "fid": "f3", "fs": _FS[market], "fields": _CLIST_FIELDS, "ut": _UT},
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        timeout=20)
    r.raise_for_status()
    d = r.json()
    data = d.get("data") or {}
    return data.get("total") or 0, data.get("diff") or []

def _clist_rows_to_cn(rows, market):
    """clist 字段 → 中文列名 dict（复用 normalize_row 的同义词表）。"""
    out = []
    for x in rows:
        code = str(x.get("f12") or "")
        daima = f'{x.get("f13")}.{code}' if market == "us" else code
        pe = x.get("f115") if market == "us" else x.get("f9")
        out.append({"代码": daima, "名称": x.get("f14"), "最新价": x.get("f2"),
                    "涨跌幅": x.get("f3"), "成交额": x.get("f6"), "换手率": x.get("f8"),
                    "量比": x.get("f10"), "市盈率-动态": pe, "市净率": x.get("f23"),
                    "总市值": x.get("f20"), "流通市值": x.get("f21"),
                    "60日涨跌幅": x.get("f24")})
    return out

def _fetch_snapshot_direct(market):
    total, first = _clist_page(market, 1)
    rows = list(first)
    pn = 2
    while len(rows) < total and pn <= 150:
        t, page = _clist_page(market, pn)
        if not page:
            break
        rows.extend(page)
        pn += 1
        time.sleep(0.3)
    if not rows:
        raise SnapshotError("clist直连无数据")
    return [normalize_row(r, market) for r in _clist_rows_to_cn(rows, market)]

def fetch_snapshot(market: str):
    import akshare as ak
    if market not in ("a", "us"):
        raise ValueError(f"unknown market: {market}")
    try:
        if market == "a":
            df = _retry(lambda: ak.stock_zh_a_spot_em(), tries=2)
        else:
            df = _retry(lambda: ak.stock_us_spot_em(), tries=2)
        return [normalize_row(row, market) for row in df.to_dict("records")]
    except SnapshotError:
        return _retry(lambda: _fetch_snapshot_direct(market), tries=2)

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

def fetch_klines(code, market, days=60, secid=None):
    import akshare as ak
    try:
        if market == "a":
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq").tail(days)
            cols = {"收盘": "close", "最高": "high", "最低": "low", "成交量": "volume"}
        else:
            # ak.stock_us_hist 需要带 eastmoney 前缀的原始代码（如 "105.AAPL"），
            # 快照归一化后的 code 是裸 ticker，必须用 secid 兜底
            df = ak.stock_us_hist(symbol=(secid or code), period="daily",
                                  adjust="qfq").tail(days)
            cols = {"收盘": "close", "最高": "high", "最低": "low", "成交量": "volume"}
        recs = df.rename(columns=cols).to_dict("records")
        return [{k: to_float(r.get(k)) for k in ("close", "high", "low", "volume")}
                for r in recs]
    except Exception:
        return []
