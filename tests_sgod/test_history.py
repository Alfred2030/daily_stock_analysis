from datetime import date, timedelta
from screener.history import RecommendHistory

RECENT = (date.today() - timedelta(days=1)).isoformat()
OLD = (date.today() - timedelta(days=30)).isoformat()

def test_record_and_recent(tmp_path):
    h = RecommendHistory(tmp_path / "h.db")
    h.record("a", ["600519", "000858"], RECENT)
    h.record("a", ["600519"], OLD)   # 旧记录
    h.record("us", ["AAPL"], RECENT)
    recent = h.recent_codes("a", days=14)
    assert "600519" in recent and "000858" in recent
    assert "AAPL" not in recent               # 市场隔离

def test_old_records_expire(tmp_path):
    h = RecommendHistory(tmp_path / "h.db")
    h.record("a", ["600000"], "2020-01-01")
    assert h.recent_codes("a", days=14) == set()

def test_idempotent_same_day(tmp_path):
    h = RecommendHistory(tmp_path / "h.db")
    h.record("a", ["600519"], RECENT)
    h.record("a", ["600519"], RECENT)   # 重复写不报错
    assert h.recent_codes("a", days=14) == {"600519"}
