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
    support = min(lows[-20:])
    resistance = max(highs[-60:] if len(highs) >= 60 else highs)
    bias = (last_price / ma20 - 1) if ma20 else 0.0
    buy_high = min(ma5 or last_price, last_price * 1.01)
    buy_low = max(support, ma20) if ma20 else support
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
