import run_daily
from screener.filters import load_sgod_config
from screener.history import RecommendHistory

CFG = load_sgod_config()

TOP = [{"code": "600519", "name": "贵州茅台", "market": "a", "score": 90.0,
        "price": 1450.0, "tags": [], "buy": {"buy_low": 1380.0,
        "buy_high": 1460.0, "support": 1350.0, "resistance": 1600.0,
        "ma20": 1400.0, "trigger": "回踩企稳", "position_hint": "标准"}}]

def test_run_session_wires_everything(tmp_path, monkeypatch):
    monkeypatch.setattr(run_daily, "run_screener", lambda *a, **k: [dict(r) for r in TOP])
    monkeypatch.setattr(run_daily, "_run_deep_pipeline", lambda codes: True)
    monkeypatch.setattr(run_daily, "fetch_industry", lambda c, m: "白酒")
    monkeypatch.setattr(run_daily, "fetch_series", lambda c, m: [])
    monkeypatch.setattr(run_daily, "finance_report", lambda *a, **k:
                        {"cards": {}, "health": {"score": 85.0, "coverage": 1.0,
                         "flags": []}, "analysis_text": "分析", "outlook_text": "展望"})
    monkeypatch.setattr(run_daily, "gather_intel", lambda cands, m:
                        {"白酒": {"stocks": ["600519"], "news": [], "assessment": "中性：观察"}})
    monkeypatch.setattr(run_daily, "advisor_report", lambda *a, **k: "组合说明")
    sent = {}
    monkeypatch.setattr(run_daily, "send_wecom", lambda md: sent.setdefault("md", md) or True)
    monkeypatch.setattr(run_daily, "DB_PATH", tmp_path / "h.db")
    result = run_daily.run_session("a", CFG, deep=True, notify=True,
                                   out_dir=tmp_path / "reports")
    assert result["pushed"] is True
    assert "贵州茅台" in sent["md"]
    assert result["top"][0]["health_score"] == 85.0     # 财务分写回候选
    assert (tmp_path / "reports").exists()

def test_dry_run_skips_push_and_history(tmp_path, monkeypatch):
    monkeypatch.setattr(run_daily, "run_screener", lambda *a, **k: [dict(r) for r in TOP])
    monkeypatch.setattr(run_daily, "fetch_industry", lambda c, m: None)
    monkeypatch.setattr(run_daily, "fetch_series", lambda c, m: [])
    monkeypatch.setattr(run_daily, "finance_report", lambda *a, **k:
                        {"cards": {}, "health": {"score": None, "coverage": 0.0,
                         "flags": []}, "analysis_text": None, "outlook_text": None})
    monkeypatch.setattr(run_daily, "gather_intel", lambda *a, **k: {})
    monkeypatch.setattr(run_daily, "advisor_report", lambda *a, **k: None)
    called = []
    monkeypatch.setattr(run_daily, "send_wecom", lambda md: called.append(md))
    db_path = tmp_path / "h.db"
    monkeypatch.setattr(run_daily, "DB_PATH", db_path)
    result = run_daily.run_session("a", CFG, deep=False, notify=False,
                                   record=False, out_dir=tmp_path / "reports")
    assert called == [] and result["pushed"] is False
    assert "600519" not in RecommendHistory(db_path).recent_codes("a", 14)

def test_no_notify_still_records_history(tmp_path, monkeypatch):
    monkeypatch.setattr(run_daily, "run_screener", lambda *a, **k: [dict(r) for r in TOP])
    monkeypatch.setattr(run_daily, "_run_deep_pipeline", lambda codes: True)
    monkeypatch.setattr(run_daily, "fetch_industry", lambda c, m: "白酒")
    monkeypatch.setattr(run_daily, "fetch_series", lambda c, m: [])
    monkeypatch.setattr(run_daily, "finance_report", lambda *a, **k:
                        {"cards": {}, "health": {"score": 85.0, "coverage": 1.0,
                         "flags": []}, "analysis_text": "分析", "outlook_text": "展望"})
    monkeypatch.setattr(run_daily, "gather_intel", lambda cands, m:
                        {"白酒": {"stocks": ["600519"], "news": [], "assessment": "中性：观察"}})
    monkeypatch.setattr(run_daily, "advisor_report", lambda *a, **k: "组合说明")
    called = []
    monkeypatch.setattr(run_daily, "send_wecom", lambda md: called.append(md))
    db_path = tmp_path / "h.db"
    monkeypatch.setattr(run_daily, "DB_PATH", db_path)
    result = run_daily.run_session("a", CFG, deep=True, notify=False,
                                   record=True, out_dir=tmp_path / "reports")
    assert called == []
    assert result["pushed"] is False
    assert "600519" in RecommendHistory(db_path).recent_codes("a", 14)

def test_resolve_risk_profile_falls_back_to_balanced(monkeypatch, capsys):
    monkeypatch.setenv("SGOD_RISK_PROFILE", "yolo")
    assert run_daily._resolve_risk_profile(CFG) == "balanced"
    assert "yolo" in capsys.readouterr().out

def test_resolve_risk_profile_passes_through_known_value(monkeypatch):
    monkeypatch.setenv("SGOD_RISK_PROFILE", "aggressive")
    assert run_daily._resolve_risk_profile(CFG) == "aggressive"

def test_resolve_capital_falls_back_on_bad_float(monkeypatch, capsys):
    monkeypatch.setenv("SGOD_CAPITAL", "not-a-number")
    assert run_daily._resolve_capital(CFG) == float(CFG["advisor"]["capital_base"])
    assert "not-a-number" in capsys.readouterr().out

def test_resolve_capital_uses_env_when_valid(monkeypatch):
    monkeypatch.setenv("SGOD_CAPITAL", "250000")
    assert run_daily._resolve_capital(CFG) == 250000.0

def test_run_session_survives_bad_env(tmp_path, monkeypatch):
    """未知风险偏好 + 非法本金不应让整场崩溃，而是告警回退默认值。"""
    monkeypatch.setenv("SGOD_RISK_PROFILE", "yolo")
    monkeypatch.setenv("SGOD_CAPITAL", "not-a-number")
    monkeypatch.setattr(run_daily, "run_screener", lambda *a, **k: [dict(r) for r in TOP])
    monkeypatch.setattr(run_daily, "_run_deep_pipeline", lambda codes: True)
    monkeypatch.setattr(run_daily, "fetch_industry", lambda c, m: "白酒")
    monkeypatch.setattr(run_daily, "fetch_series", lambda c, m: [])
    monkeypatch.setattr(run_daily, "finance_report", lambda *a, **k:
                        {"cards": {}, "health": {"score": 85.0, "coverage": 1.0,
                         "flags": []}, "analysis_text": "分析", "outlook_text": "展望"})
    monkeypatch.setattr(run_daily, "gather_intel", lambda cands, m: {})
    monkeypatch.setattr(run_daily, "advisor_report", lambda *a, **k: "组合说明")
    monkeypatch.setattr(run_daily, "send_wecom", lambda md: True)
    monkeypatch.setattr(run_daily, "DB_PATH", tmp_path / "h.db")
    result = run_daily.run_session("a", CFG, deep=True, notify=True,
                                   out_dir=tmp_path / "reports")
    assert result["top"][0]["health_score"] == 85.0     # 没崩，正常跑完

def test_deep_failure_sets_flag_and_warns(tmp_path, monkeypatch):
    monkeypatch.setattr(run_daily, "run_screener", lambda *a, **k: [dict(r) for r in TOP])
    monkeypatch.setattr(run_daily, "_run_deep_pipeline", lambda codes: False)
    monkeypatch.setattr(run_daily, "fetch_industry", lambda c, m: "白酒")
    monkeypatch.setattr(run_daily, "fetch_series", lambda c, m: [])
    monkeypatch.setattr(run_daily, "finance_report", lambda *a, **k:
                        {"cards": {}, "health": {"score": 85.0, "coverage": 1.0,
                         "flags": []}, "analysis_text": "分析", "outlook_text": "展望"})
    monkeypatch.setattr(run_daily, "gather_intel", lambda cands, m:
                        {"白酒": {"stocks": ["600519"], "news": [], "assessment": "中性：观察"}})
    monkeypatch.setattr(run_daily, "advisor_report", lambda *a, **k: "组合说明")
    sent = {}
    monkeypatch.setattr(run_daily, "send_wecom", lambda md: sent.setdefault("md", md) or True)
    monkeypatch.setattr(run_daily, "DB_PATH", tmp_path / "h.db")
    result = run_daily.run_session("a", CFG, deep=True, notify=True,
                                   out_dir=tmp_path / "reports")
    assert result["deep_ok"] is False
    assert sent["md"].startswith("> ⚠ 深度分析流水线失败")
