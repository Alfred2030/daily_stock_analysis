import pytest
import screener.snapshot as snap
from screener.snapshot import SnapshotError, _fetch_snapshot_direct, fetch_snapshot


def test_fetch_snapshot_direct_paginates_and_normalizes(monkeypatch):
    page1 = [{"f12": f"6001{i:02d}", "f13": 0, "f14": f"股{i}", "f2": 10.0 + i,
              "f3": 1.0, "f6": 5e8, "f8": 3.0, "f9": 10 + i, "f10": 1.2,
              "f23": 1.5, "f20": 3e10, "f21": 3e10, "f24": 5.0}
             for i in range(20)]
    page2 = [{"f12": f"6002{i:02d}", "f13": 0, "f14": f"股b{i}", "f2": 20.0 + i,
              "f3": 1.0, "f6": 5e8, "f8": 3.0, "f9": 12 + i, "f10": 1.2,
              "f23": 1.5, "f20": 3e10, "f21": 3e10, "f24": 5.0}
             for i in range(5)]

    calls = []

    def fake_clist_page(market, pn, pz=1000):
        calls.append(pn)
        if pn == 1:
            return 25, page1
        elif pn == 2:
            return 25, page2
        return 25, []

    monkeypatch.setattr(snap, "_clist_page", fake_clist_page)
    monkeypatch.setattr(snap.time, "sleep", lambda s: None)

    rows = _fetch_snapshot_direct("a")
    assert len(rows) == 25
    first = rows[0]
    assert first["code"] == "600100"
    assert first["price"] == 10.0
    assert first["pe"] == 10


def test_fetch_snapshot_direct_us_row_maps_secid_and_pe(monkeypatch):
    row = {"f12": "AAPL", "f13": 105, "f14": "苹果", "f2": 190.0, "f3": 1.5,
           "f6": 1e9, "f8": 1.0, "f9": None, "f10": 1.0, "f23": 40.0,
           "f20": 3e12, "f21": 3e12, "f24": 10.0, "f115": 30.5}

    def fake_clist_page(market, pn, pz=1000):
        if pn == 1:
            return 1, [row]
        return 1, []

    monkeypatch.setattr(snap, "_clist_page", fake_clist_page)
    monkeypatch.setattr(snap.time, "sleep", lambda s: None)

    rows = _fetch_snapshot_direct("us")
    assert len(rows) == 1
    r = rows[0]
    assert r["code"] == "AAPL"
    assert r["secid"] == "105.AAPL"
    assert r["pe"] == 30.5


def test_fetch_snapshot_falls_back_to_direct_on_akshare_failure(monkeypatch):
    class FakeAk:
        def stock_zh_a_spot_em(self):
            raise RuntimeError("RemoteDisconnected")

    monkeypatch.setitem(__import__("sys").modules, "akshare", FakeAk())
    monkeypatch.setattr(snap.time, "sleep", lambda s: None)

    row = {"f12": "600100", "f13": 0, "f14": "股", "f2": 10.0, "f3": 1.0,
           "f6": 5e8, "f8": 3.0, "f9": 10, "f10": 1.2, "f23": 1.5,
           "f20": 3e10, "f21": 3e10, "f24": 5.0}

    def fake_clist_page(market, pn, pz=1000):
        if pn == 1:
            return 1, [row]
        return 1, []

    monkeypatch.setattr(snap, "_clist_page", fake_clist_page)

    rows = fetch_snapshot("a")
    assert len(rows) == 1
    assert rows[0]["code"] == "600100"


def test_fetch_snapshot_raises_when_both_fail(monkeypatch):
    class FakeAk:
        def stock_zh_a_spot_em(self):
            raise RuntimeError("RemoteDisconnected")

    monkeypatch.setitem(__import__("sys").modules, "akshare", FakeAk())
    monkeypatch.setattr(snap.time, "sleep", lambda s: None)

    def fake_clist_page(market, pn, pz=1000):
        raise RuntimeError("network down")

    monkeypatch.setattr(snap, "_clist_page", fake_clist_page)

    with pytest.raises(SnapshotError):
        fetch_snapshot("a")
