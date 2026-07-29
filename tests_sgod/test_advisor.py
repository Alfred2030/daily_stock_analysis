from screener.filters import load_sgod_config
from portfolio_advisor.allocate import allocate
from portfolio_advisor.report import build_advisor_prompt

CFG = load_sgod_config()

def _cand(code, score, price, industry, hint="标准", health=80.0):
    return {"code": code, "name": f"N{code}", "score": score, "price": price,
            "market": "a", "industry": industry, "health_score": health,
            "buy": {"buy_low": price * 0.95, "buy_high": price,
                    "support": price * 0.9, "resistance": price * 1.2,
                    "ma20": price * 0.97, "trigger": "回踩企稳",
                    "position_hint": hint}}

CANDS = [_cand("600519", 90, 1450.0, "白酒"), _cand("000858", 85, 130.0, "白酒"),
         _cand("300750", 80, 250.0, "电池"), _cand("600036", 75, 35.0, "银行"),
         _cand("601318", 70, 50.0, "保险"), _cand("000001", 65, 12.0, "银行")]

def test_balanced_allocation_respects_caps():
    a = allocate(CANDS, 100000, "balanced", CFG)
    prof = CFG["advisor"]["risk_profiles"]["balanced"]
    total = sum(p["amount"] for p in a["picks"])
    assert a["cash_reserve"] >= prof["min_cash"] * 100000 - 1
    assert all(p["amount"] <= prof["max_pos"] * 100000 + 1 for p in a["picks"])
    by_ind = {}
    for p in a["picks"]:
        ind = next(c["industry"] for c in CANDS if c["code"] == p["code"])
        by_ind[ind] = by_ind.get(ind, 0) + p["amount"]
    assert all(v <= prof["max_industry"] * 100000 + 1 for v in by_ind.values())
    assert len(a["picks"]) <= prof["n_picks"]

def test_a_share_lots_rounded_and_unaffordable_dropped():
    a = allocate(CANDS, 30000, "conservative", CFG)   # 3万本金买不起茅台一手
    codes = [p["code"] for p in a["picks"]]
    assert "600519" not in codes                      # 1450×100 > 10%×30000
    assert all(p["shares"] % 100 == 0 for p in a["picks"])

def test_wait_hint_excluded():
    cands = [_cand("600000", 95, 10.0, "银行", hint="观望")] + CANDS[3:]
    a = allocate(cands, 100000, "balanced", CFG)
    assert "600000" not in [p["code"] for p in a["picks"]]

def test_batches_split_60_40():
    a = allocate(CANDS, 100000, "balanced", CFG)
    p = a["picks"][0]
    assert abs(p["first_batch"] + p["add_batch"] - p["amount"]) < 1
    assert p["first_batch"] > p["add_batch"]

def test_prompt_mentions_disclaimer_inputs():
    a = allocate(CANDS, 100000, "balanced", CFG)
    prompt = build_advisor_prompt(a, "a")
    assert "止损" in prompt and "风险" in prompt

def test_zero_capital_returns_empty():
    a = allocate(CANDS, 0, "balanced", CFG)
    assert a["picks"] == [] and a["cash_pct"] == 100.0

def test_us_market_fractional_amount():
    us = [{**_cand("AAPL", 90, 228.0, "Technology"), "market": "us"}]
    a = allocate(us, 100000, "balanced", CFG)
    assert a["picks"] and a["picks"][0]["shares"] is None
    assert a["picks"][0]["amount"] <= 15000 + 1
