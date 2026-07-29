from screener.filters import hard_filter, load_sgod_config

CFG = load_sgod_config()

def _row(**kw):
    base = {"code": "600000", "name": "浦发银行", "market": "a", "price": 10.0,
            "pct_chg": 1.0, "turnover_amt": 5e8, "volume_ratio": 1.0,
            "turnover_rate": 2.0, "pe": 8.0, "pb": 0.6, "total_mv": 3e10,
            "circ_mv": 3e10, "pct_60d": 3.0, "listing_days": 1000}
    base.update(kw)
    return base

def test_filters_out_st_and_cheap_and_illiquid():
    rows = [_row(), _row(name="ST某某"), _row(price=1.5), _row(turnover_amt=5e7),
            _row(pe=-3.0), _row(listing_days=10)]
    kept = hard_filter(rows, "a", CFG)
    assert len(kept) == 1 and kept[0]["name"] == "浦发银行"

def test_subnew_gets_tag_not_dropped():
    kept = hard_filter([_row(listing_days=100)], "a", CFG)
    assert kept and "次新" in kept[0]["tags"]

def test_us_filters_price_and_liquidity():
    rows = [_row(market="us", code="AAPL", price=228.0, turnover_amt=8e9, pe=30.0),
            _row(market="us", code="PENNY", price=1.2),
            _row(market="us", code="THIN", turnover_amt=1e7)]
    kept = hard_filter(rows, "us", CFG)
    assert [r["code"] for r in kept] == ["AAPL"]

def test_missing_fields_do_not_crash():
    kept = hard_filter([_row(pe=None, pct_60d=None)], "a", CFG)
    assert kept  # PE 缺失不按亏损处理，放行交给打分层

def test_us_filters_out_non_common_stock_instruments():
    rows = [
        _row(market="us", code="AAPL", name="苹果", price=228.0, turnover_amt=8e9, pe=30.0),
        _row(market="us", code="AAPL.U", name="苹果单位", price=228.0, turnover_amt=8e9, pe=30.0),
        _row(market="us", code="AAPL_WS", name="苹果认股权证", price=228.0, turnover_amt=8e9, pe=30.0),
        _row(market="us", code="SPY", name="SPDR ETF信托", price=228.0, turnover_amt=8e9, pe=30.0),
        _row(market="us", code="XYZ", name="XYZ优先股", price=228.0, turnover_amt=8e9, pe=30.0),
    ]
    kept = hard_filter(rows, "us", CFG)
    assert [r["code"] for r in kept] == ["AAPL"]
