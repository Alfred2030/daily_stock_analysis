import industry_intel.run as intel

def test_build_queries_market_specific():
    qa = intel.build_queries("半导体", "a")
    qus = intel.build_queries("Technology", "us")
    assert any("政策" in q for q in qa)
    assert any(("美联储" in q) or ("关税" in q) for q in qus)
    assert all(len(qs) <= 2 for qs in (qa, qus))

def test_gather_intel_groups_and_degrades(monkeypatch):
    monkeypatch.setattr(intel, "_search", lambda q: ["新闻标题1", "新闻标题2"])
    monkeypatch.setattr(intel, "chat", lambda *a, **k: "利好：……影响窗口1-2月")
    cands = [{"code": "600519", "industry": "白酒"},
             {"code": "000858", "industry": "白酒"},
             {"code": "300750", "industry": "电池"}]
    out = intel.gather_intel(cands, "a")
    assert set(out) == {"白酒", "电池"}
    assert out["白酒"]["stocks"] == ["600519", "000858"]
    assert out["白酒"]["assessment"].startswith("利好")

def test_no_search_key_returns_empty_news(monkeypatch):
    monkeypatch.setattr(intel, "_search", lambda q: [])
    monkeypatch.setattr(intel, "chat", lambda *a, **k: None)
    out = intel.gather_intel([{"code": "AAPL", "industry": "Technology"}], "us")
    assert out["Technology"]["news"] == []
    assert out["Technology"]["assessment"] is None
