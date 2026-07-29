from sgod.wecom import build_daily_markdown
from sgod.html_report import write_html_report

TOP = [{"code": "600519", "name": "贵州茅台", "score": 90.0, "tags": [],
        "price": 1450.0, "industry": "白酒", "health_score": 85.0,
        "buy": {"buy_low": 1380.0, "buy_high": 1460.0, "support": 1350.0,
                "resistance": 1600.0, "ma20": 1400.0,
                "trigger": "回踩企稳", "position_hint": "标准"}}]
ALLOC = {"picks": [{"code": "600519", "name": "贵州茅台", "amount": 14500.0,
          "weight": 14.5, "shares": 100, "first_batch": 8700.0,
          "add_batch": 5800.0, "buy": TOP[0]["buy"]}],
         "cash_reserve": 85500.0, "cash_pct": 85.5}
INTEL = {"白酒": {"stocks": ["600519"], "news": ["标题"], "assessment": "中性：短期无催化"}}

def test_markdown_contains_key_sections_and_disclaimer():
    md = build_daily_markdown("a", "2026-07-29", TOP, ALLOC, "组合说明",
                              INTEL, "https://stock.cxodex.com")
    assert "贵州茅台" in md and "1380.0" in md
    assert "不构成投资建议" in md
    assert len(md.encode("utf-8")) <= 4000

def test_markdown_truncates_when_oversized():
    intel = {f"行业{i}": {"stocks": ["600519"], "news": ["x" * 50] * 8,
             "assessment": "中性：" + "很长的评估" * 30} for i in range(20)}
    md = build_daily_markdown("a", "2026-07-29", TOP * 5, ALLOC, "说明" * 100,
                              intel, "https://stock.cxodex.com")
    assert len(md.encode("utf-8")) <= 4000

def test_html_report_written_with_index(tmp_path):
    fmap = {"600519": {"cards": {"peer": {"gross_margin": 91.0}, "mgmt": {},
            "risk": {}}, "health": {"score": 85.0, "coverage": 1.0, "flags": []},
            "analysis_text": "分析", "outlook_text": "展望"}}
    p = write_html_report(tmp_path, "a", "2026-07-29", TOP, fmap, ALLOC,
                          "组合说明", INTEL)
    assert p.exists() and (tmp_path / "index.html").exists()
    html = p.read_text(encoding="utf-8")
    assert "贵州茅台" in html and "展望" in html and "不构成投资建议" in html
