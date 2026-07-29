# tests_sgod/test_imds_scoring.py
from imds_finance.scoring import health_score

GOOD_PEER = {"gross_margin": 45.0, "net_margin": 20.0, "roe": 18.0,
             "debt_ratio": 35.0, "inv_turnover": 6.0, "asset_turnover": 0.8,
             "ar_turnover": 8.0}
GOOD_MGMT = {"cash_quality": 1.2, "expense_rates": {"sales": 5.0, "admin": 4.0,
             "fin": 1.0, "rd": 5.0}, "rev_yoy": 20.0, "profit_yoy": 25.0,
             "growth_match": "利润快于收入"}
GOOD_RISK = {"current_ratio": 2.0, "quick_ratio": 1.5, "ar_vs_rev_gap": 0.0,
             "inv_vs_rev_gap": -2.0, "goodwill_ratio": 5.0}

def test_good_company_scores_high():
    r = health_score(GOOD_PEER, GOOD_MGMT, GOOD_RISK)
    assert r["score"] is not None and r["score"] >= 70
    assert r["flags"] == []

def test_bad_signals_lower_score_and_flag():
    bad_mgmt = {**GOOD_MGMT, "cash_quality": 0.2}
    bad_risk = {**GOOD_RISK, "ar_vs_rev_gap": 30.0, "goodwill_ratio": 60.0}
    r = health_score(GOOD_PEER, bad_mgmt, bad_risk)
    good = health_score(GOOD_PEER, GOOD_MGMT, GOOD_RISK)
    assert r["score"] < good["score"]
    assert any("现金" in f for f in r["flags"])
    assert any("商誉" in f for f in r["flags"])

def test_insufficient_coverage_returns_none():
    empty = {k: None for k in GOOD_PEER}
    empty_m = {"cash_quality": None, "expense_rates": {k: None for k in
               ("sales", "admin", "fin", "rd")}, "rev_yoy": None,
               "profit_yoy": None, "growth_match": None}
    empty_r = {k: None for k in GOOD_RISK}
    r = health_score(empty, empty_m, empty_r)
    assert r["score"] is None and r["coverage"] < 0.4

def test_peer_median_comparison_adjusts_score():
    weak_median = {**GOOD_PEER, "gross_margin": 20.0, "roe": 8.0}
    vs_weak = health_score(GOOD_PEER, GOOD_MGMT, GOOD_RISK, peer_median=weak_median)
    vs_none = health_score(GOOD_PEER, GOOD_MGMT, GOOD_RISK)
    assert vs_weak["score"] >= vs_none["score"]    # 显著优于同行 → 加分

def test_missing_keys_do_not_crash():
    """缺键不再KeyError——绝不抛错"""
    # 完全空的字典：应返回None score和空flags
    r = health_score({}, {}, {})
    assert r["score"] is None and r["flags"] == []

    # 只有1个指标：coverage不足（1/10 < 0.4）
    r2 = health_score({"roe": 15.0}, {}, {})
    assert r2["score"] is None and r2["coverage"] < 0.4
