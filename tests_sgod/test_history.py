from screener.history import RecommendHistory

def test_record_and_recent(tmp_path):
    h = RecommendHistory(tmp_path / "h.db")
    h.record("a", ["600519", "000858"], "2026-07-28")
    h.record("a", ["600519"], "2026-07-01")   # 旧记录
    h.record("us", ["AAPL"], "2026-07-28")
    recent = h.recent_codes("a", days=14)
    assert "600519" in recent and "000858" in recent
    assert "AAPL" not in recent               # 市场隔离

def test_old_records_expire(tmp_path):
    h = RecommendHistory(tmp_path / "h.db")
    h.record("a", ["600000"], "2020-01-01")
    assert h.recent_codes("a", days=14) == set()

def test_idempotent_same_day(tmp_path):
    h = RecommendHistory(tmp_path / "h.db")
    h.record("a", ["600519"], "2026-07-28")
    h.record("a", ["600519"], "2026-07-28")   # 重复写不报错
    assert h.recent_codes("a", days=14) == {"600519"}
