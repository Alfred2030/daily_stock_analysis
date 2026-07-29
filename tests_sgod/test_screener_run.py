import screener.run as srun
from screener.filters import load_sgod_config
from screener.history import RecommendHistory

CFG = load_sgod_config()

def _fake_snapshot(market):
    rows = []
    for i in range(40):
        rows.append({"code": f"6001{i:02d}", "name": f"股{i}", "market": "a",
                     "price": 10.0 + i, "pct_chg": 1.0, "turnover_amt": 5e8,
                     "volume_ratio": 1.2, "turnover_rate": 3.0, "pe": 10 + i,
                     "pb": 1.5, "total_mv": 3e10, "circ_mv": 3e10,
                     "pct_60d": 5.0, "listing_days": None})
    return rows

def _fake_listing_days(codes):
    return {c: 500 for c in codes}

def _fake_klines(code, market, days=60):
    return [{"close": 10 + i * 0.05, "high": 10.3 + i * 0.05,
             "low": 9.8 + i * 0.05, "volume": 1e6} for i in range(60)]

def test_run_screener_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(srun, "fetch_snapshot", _fake_snapshot)
    monkeypatch.setattr(srun, "fetch_listing_days_a", _fake_listing_days)
    monkeypatch.setattr(srun, "fetch_klines", _fake_klines)
    h = RecommendHistory(tmp_path / "h.db")
    h.record("a", ["600139"], "2026-07-28")  # 最高分之一提前进历史
    top = srun.run_screener("a", CFG, h)
    assert len(top) == CFG["screener"]["top_n"]
    assert all(r["code"] != "600139" for r in top)      # 去重生效
    assert all("buy" in r and r["buy"] for r in top)     # 每只带买点
    assert all("score" in r for r in top)
