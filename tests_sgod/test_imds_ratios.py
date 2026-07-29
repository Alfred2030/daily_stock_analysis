from imds_finance.ratios import peer_card, mgmt_card, risk_card

def _q(period, rev, profit, **kw):
    base = {"period": period, "revenue": rev, "net_profit": profit,
            "gross_profit": rev * 0.4, "op_cashflow": profit * 1.1,
            "total_assets": 1000.0, "total_liab": 400.0, "equity": 600.0,
            "ar": 100.0, "inventory": 80.0, "goodwill": 30.0,
            "current_assets": 500.0, "current_liab": 250.0,
            "sales_exp": rev * 0.05, "admin_exp": rev * 0.04,
            "fin_exp": rev * 0.01, "rd_exp": rev * 0.03}
    base.update(kw)
    return base

SERIES = [_q(f"202{y}Q{q}", 100.0 + i * 5, 10.0 + i)
          for i, (y, q) in enumerate((y, q) for y in (4, 5) for q in range(1, 5))]

def test_peer_card_ttm():
    c = peer_card(SERIES)
    assert abs(c["gross_margin"] - 40.0) < 0.5     # 毛利率恒 40%
    assert c["debt_ratio"] == 40.0                 # 400/1000
    assert c["roe"] is not None and c["inv_turnover"] is not None

def test_mgmt_card_growth_and_cash():
    c = mgmt_card(SERIES)
    assert c["cash_quality"] and abs(c["cash_quality"] - 1.1) < 0.01
    assert c["rev_yoy"] is not None and c["rev_yoy"] > 0
    assert c["expense_rates"]["rd"] is not None

def test_risk_card_ratios():
    c = risk_card(SERIES)
    assert c["current_ratio"] == 2.0               # 500/250
    assert c["goodwill_ratio"] == 5.0              # 30/600

def test_insufficient_data_returns_none_fields():
    c = peer_card(SERIES[:2])                      # 不足4季无TTM
    assert c["gross_margin"] is None
    c2 = mgmt_card(SERIES[:5])                     # 不足8季无YoY
    assert c2["rev_yoy"] is None

def test_yoy_loss_to_profit_turnaround_positive():
    # 前4季净利均为-25(亏损100), 近4季净利均为+12.5(盈利50) → YoY = (50-(-100))/100*100 = +150%
    series = [_q(f"T{i}", 100.0, -25.0) for i in range(4)] + \
             [_q(f"T{i+4}", 100.0, 12.5) for i in range(4)]
    c = mgmt_card(series)
    assert c["profit_yoy"] == 150.0
