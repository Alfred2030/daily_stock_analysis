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

def test_downtrend_zone_never_inverted():
    closes = [30 - i * 0.9 for i in range(20)]      # 急跌
    z = buy_zone(_k(closes), closes[-1])
    assert z["buy_low"] <= z["buy_high"]
    assert z["position_hint"] != "标准"

def test_gap_down_zone_never_inverted():
    closes = [20.0] * 55 + [14.0] * 5               # 跳空破位
    z = buy_zone(_k(closes), 14.0)
    assert z["buy_low"] <= z["buy_high"]
