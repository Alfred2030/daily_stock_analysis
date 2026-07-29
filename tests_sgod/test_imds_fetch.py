import pandas as pd
import imds_finance.fetch as ff

def _profit_df():
    # REPORT_TYPE 顺序按 eastmoney 实际返回习惯（新→旧），代码内部会重新按日期排序
    return pd.DataFrame({
        "REPORT_DATE": ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31",
                        "2026-03-31"],
        "REPORT_TYPE": ["一季报", "中报", "三季报", "年报", "一季报"],
        "TOTAL_OPERATE_INCOME": [100.0, 210.0, 330.0, 460.0, 120.0],
        "PARENT_NETPROFIT": [10.0, 21.0, 33.0, 46.0, 12.0],
        "OPERATE_COST": [60.0, 126.0, 198.0, 276.0, 70.0],
        "SALE_EXPENSE": [5.0, 10.0, 15.0, 20.0, 6.0],
        "MANAGE_EXPENSE": [4.0, 8.0, 12.0, 16.0, 5.0],
        "FINANCE_EXPENSE": [1.0, 2.0, 3.0, 4.0, 1.0],
        "RESEARCH_EXPENSE": [3.0, 6.0, 9.0, 12.0, 3.0],
    })

def _balance_df():
    return pd.DataFrame({
        "REPORT_DATE": ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31",
                        "2026-03-31"],
        "TOTAL_ASSETS": [1000.0, 1010.0, 1020.0, 1030.0, 1040.0],
        "TOTAL_LIABILITIES": [400.0, 410.0, 420.0, 430.0, 440.0],
        "TOTAL_PARENT_EQUITY": [600.0, 600.0, 600.0, 600.0, 600.0],
        "ACCOUNTS_RECE": [50.0, 55.0, 60.0, 65.0, 70.0],
        "INVENTORY": [80.0, 82.0, 84.0, 86.0, 88.0],
        "GOODWILL": [30.0] * 5,
        "TOTAL_CURRENT_ASSETS": [500.0] * 5,
        "TOTAL_CURRENT_LIAB": [250.0] * 5,
    })

def _cash_df():
    return pd.DataFrame({
        "REPORT_DATE": ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31",
                        "2026-03-31"],
        "NETCASH_OPERATE": [12.0, 25.0, 39.0, 54.0, 13.0],
    })

def test_a_series_decumulates_ytd_income_and_cashflow(monkeypatch):
    monkeypatch.setattr(ff, "_em_statements",
                        lambda code: (_profit_df(), _balance_df(), _cash_df()))
    series = ff._a_series("600519", quarters=8)
    assert [s["period"] for s in series] == \
        ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31"]
    # 累计 100/210/330/460 → 单季度 100/110/120/130；跨年后 Q1 重置为 120
    assert [s["revenue"] for s in series] == [100.0, 110.0, 120.0, 130.0, 120.0]
    assert [s["net_profit"] for s in series] == [10.0, 11.0, 12.0, 13.0, 12.0]
    assert [s["op_cashflow"] for s in series] == [12.0, 13.0, 14.0, 15.0, 13.0]
    # 营业成本累计 60/126/198/276 → 单季度 60/66/72/78，跨年重置为 70
    # 毛利润 = 单季度收入 - 单季度成本
    assert series[0]["gross_profit"] == 100.0 - 60.0
    assert series[-1]["gross_profit"] == 120.0 - 70.0
    # 资产负债表是时点数，原样透传，不反算
    assert series[0]["total_assets"] == 1000.0
    assert series[-1]["total_assets"] == 1040.0
    assert series[0]["equity"] == 600.0

def test_a_series_missing_column_returns_none(monkeypatch):
    profit = _profit_df().drop(columns=["RESEARCH_EXPENSE"])
    monkeypatch.setattr(ff, "_em_statements",
                        lambda code: (profit, _balance_df(), _cash_df()))
    series = ff._a_series("600519", quarters=8)
    assert all(s["rd_exp"] is None for s in series)

def test_fetch_series_total_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(ff, "_em_statements",
                        lambda code: (_ for _ in ()).throw(RuntimeError("网络挂了")))
    assert ff.fetch_series("600519", "a") == []

def test_us_series_maps_yf_frames(monkeypatch):
    fin = pd.DataFrame({pd.Timestamp("2026-03-31"): {"Total Revenue": 100.0,
                        "Net Income": 10.0, "Gross Profit": 40.0},
                        pd.Timestamp("2025-12-31"): {"Total Revenue": 95.0,
                        "Net Income": 9.0, "Gross Profit": 38.0}})
    bal = pd.DataFrame({pd.Timestamp("2026-03-31"): {"Total Assets": 1000.0,
                        "Total Liabilities Net Minority Interest": 400.0,
                        "Stockholders Equity": 600.0}})
    cf = pd.DataFrame({pd.Timestamp("2026-03-31"): {"Operating Cash Flow": 12.0}})
    monkeypatch.setattr(ff, "_yf_frames", lambda code: (fin, bal, cf))
    series = ff._us_series("AAPL", quarters=8)
    assert series[-1]["revenue"] == 100.0
    assert series[-1]["total_assets"] == 1000.0
    assert series[-1]["op_cashflow"] == 12.0
    assert series[0]["total_assets"] is None       # 早期季度资产表缺 → None

def test_us_series_period_is_date_string(monkeypatch):
    fin = pd.DataFrame({pd.Timestamp("2026-03-31"): {"Total Revenue": 100.0}})
    monkeypatch.setattr(ff, "_yf_frames", lambda code: (fin, pd.DataFrame(), pd.DataFrame()))
    series = ff._us_series("AAPL", quarters=8)
    assert series[-1]["period"] == "2026-03-31"

def test_fetch_industry_missing_returns_none(monkeypatch):
    # 模拟 akshare 模块及其函数，返回不含"行业"键的DataFrame
    class MockAkshare:
        @staticmethod
        def stock_individual_info_em(symbol):
            return pd.DataFrame({"item": ["名称"], "value": ["某股"]})

    import sys
    monkeypatch.setitem(sys.modules, "akshare", MockAkshare())
    result = ff.fetch_industry("600519", "a")
    assert result is None
