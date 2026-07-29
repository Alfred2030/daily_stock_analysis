# tests_sgod/test_scoring.py
from screener.filters import load_sgod_config
from screener.scoring import score_row, rank_top

CFG = load_sgod_config()

def _row(**kw):
    base = {"code": "600000", "name": "样本", "market": "a", "price": 10.0,
            "pct_chg": 1.0, "turnover_amt": 5e8, "volume_ratio": 1.2,
            "turnover_rate": 3.0, "pe": 15.0, "pb": 1.5, "total_mv": 3e10,
            "circ_mv": 3e10, "pct_60d": 8.0, "listing_days": 1000, "tags": []}
    base.update(kw)
    return base

def test_score_in_range_and_has_parts():
    s = score_row(_row(), CFG)
    assert 0 <= s["score"] <= 100
    assert set(s["score_parts"]) == {"finance", "technical", "flow"}

def test_missing_data_scores_neutral_50():
    s = score_row(_row(pe=None, pb=None), CFG)
    assert s["score_parts"]["finance"] == 50.0

def test_reasonable_ordering():
    good = score_row(_row(pe=12, pb=1.2, pct_60d=12, volume_ratio=1.8,
                          turnover_rate=5.0), CFG)
    bad = score_row(_row(pe=200, pb=20, pct_60d=-30, volume_ratio=0.3,
                         turnover_rate=0.2), CFG)
    assert good["score"] > bad["score"]

def test_rank_top_excludes_and_limits():
    rows = [score_row(_row(code=f"6000{i:02d}"), CFG) for i in range(30)]
    top = rank_top(rows, CFG, exclude_codes={"600001", "600002"})
    assert len(top) == CFG["screener"]["top_n"]
    assert all(r["code"] not in {"600001", "600002"} for r in top)
