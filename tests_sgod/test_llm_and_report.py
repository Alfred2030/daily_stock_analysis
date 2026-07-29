import sgod.llm as llm
from imds_finance.report import build_prompt, finance_report

SERIES = [{"period": f"2025Q{q}", "revenue": 100.0 + q, "net_profit": 10.0,
           "gross_profit": 40.0, "op_cashflow": 11.0, "total_assets": 1000.0,
           "total_liab": 400.0, "equity": 600.0, "ar": 100.0, "inventory": 80.0,
           "goodwill": 30.0, "current_assets": 500.0, "current_liab": 250.0,
           "sales_exp": 5.0, "admin_exp": 4.0, "fin_exp": 1.0, "rd_exp": 3.0}
          for q in range(1, 5)] * 2

def test_build_prompt_contains_cards_and_asks_two_sections():
    p = build_prompt("600519", "贵州茅台", "a", SERIES, industry="白酒")
    assert "贵州茅台" in p and "白酒" in p
    assert "管理层分析和关注" in p and "财务展望" in p
    assert "毛利率" in p          # 三卡数据进了提示词

def test_chat_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr(llm, "_post", lambda *a, **k: None)
    assert llm.chat("hi") is None

def test_finance_report_degrades_without_llm(monkeypatch):
    import imds_finance.report as rep
    monkeypatch.setattr(rep, "chat", lambda *a, **k: None)
    r = finance_report("600519", "贵州茅台", "a", SERIES)
    assert r["health"]["score"] is not None
    assert r["analysis_text"] is None      # LLM 挂了不臆造文字
    assert r["cards"]["peer"]["gross_margin"] is not None
