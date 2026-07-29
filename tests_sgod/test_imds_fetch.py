import pandas as pd
import imds_finance.fetch as ff

def test_a_series_maps_synonyms(monkeypatch):
    df = pd.DataFrame({
        "选项": ["常用指标"] * 4,
        "指标": ["营业总收入", "归母净利润", "经营现金流量净额", "资产负债率"],
        "20260331": [100.0, 10.0, 12.0, 40.0],
        "20251231": [95.0, 9.0, 11.0, 41.0],
    })
    monkeypatch.setattr(ff, "_ak_financial_abstract", lambda code: df)
    series = ff._a_series("600519", quarters=8)
    assert len(series) == 2
    assert series[-1]["period"] == "20260331"      # 旧→新排序
    assert series[-1]["revenue"] == 100.0
    assert series[-1]["net_profit"] == 10.0
    assert series[-1]["gross_profit"] is None      # fixture 没给 → None

def test_fetch_series_total_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(ff, "_ak_financial_abstract",
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
