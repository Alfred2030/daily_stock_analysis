import pytest
import screener.snapshot as snap
from screener.snapshot import (SnapshotError, _fetch_snapshot_direct,
                               _us_klines_tencent, fetch_klines, fetch_snapshot)


def test_fetch_snapshot_direct_paginates_and_normalizes(monkeypatch):
    page1 = [{"f12": f"6001{i:02d}", "f13": 0, "f14": f"股{i}", "f2": 10.0 + i,
              "f3": 1.0, "f6": 5e8, "f8": 3.0, "f9": 10 + i, "f10": 1.2,
              "f23": 1.5, "f20": 3e10, "f21": 3e10, "f24": 5.0}
             for i in range(100)]
    page2 = [{"f12": f"6002{i:02d}", "f13": 0, "f14": f"股b{i}", "f2": 20.0 + i,
              "f3": 1.0, "f6": 5e8, "f8": 3.0, "f9": 12 + i, "f10": 1.2,
              "f23": 1.5, "f20": 3e10, "f21": 3e10, "f24": 5.0}
             for i in range(100)]
    page3 = [{"f12": f"6003{i:02d}", "f13": 0, "f14": f"股c{i}", "f2": 30.0 + i,
              "f3": 1.0, "f6": 5e8, "f8": 3.0, "f9": 14 + i, "f10": 1.2,
              "f23": 1.5, "f20": 3e10, "f21": 3e10, "f24": 5.0}
             for i in range(50)]

    calls = []

    def fake_clist_page(market, pn, pz=100):
        calls.append(pn)
        if pn == 1:
            return 250, page1
        elif pn == 2:
            return 250, page2
        elif pn == 3:
            return 250, page3
        return 250, []

    monkeypatch.setattr(snap, "_clist_page", fake_clist_page)
    monkeypatch.setattr(snap.time, "sleep", lambda s: None)

    rows = _fetch_snapshot_direct("a")
    assert len(rows) == 250
    first = rows[0]
    assert first["code"] == "600100"
    assert first["price"] == 10.0
    assert first["pe"] == 10


def test_fetch_snapshot_direct_us_row_maps_secid_and_pe(monkeypatch):
    row = {"f12": "AAPL", "f13": 105, "f14": "苹果", "f2": 190.0, "f3": 1.5,
           "f6": 1e9, "f8": 1.0, "f9": None, "f10": 1.0, "f23": 40.0,
           "f20": 3e12, "f21": 3e12, "f24": 10.0, "f115": 30.5}

    def fake_clist_page(market, pn, pz=100):
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

    def fake_clist_page(market, pn, pz=100):
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

    def fake_clist_page(market, pn, pz=100):
        raise RuntimeError("network down")

    monkeypatch.setattr(snap, "_clist_page", fake_clist_page)

    with pytest.raises(SnapshotError):
        fetch_snapshot("a")


def _tx_payload(key, n=70):
    day = [[f"2026-04-{i%28+1:02d}", str(100.0 + i), str(101.0 + i),
            str(103.0 + i), str(99.0 + i), str(1000 + i)] for i in range(n)]
    return {"code": 0, "data": {key: {"day": day}}}


def test_us_klines_tencent_maps_fields(monkeypatch):
    monkeypatch.setattr(snap, "_tx_kline_page",
                        lambda param: _tx_payload("usABG.N"))
    rows = _us_klines_tencent("ABG", "106.ABG", days=60)
    assert len(rows) == 60
    # 腾讯行格式 [date, open, close, high, low, volume] → close=x[2]
    assert rows[-1]["close"] == 170.0 and rows[-1]["high"] == 172.0
    assert rows[-1]["low"] == 168.0 and rows[-1]["volume"] == 1069.0


def test_us_klines_tencent_suffix_retry(monkeypatch):
    def fake_page(param):
        key = param.split(",", 1)[0]
        if key == "usXYZ.OQ":
            return _tx_payload("usXYZ.OQ", n=30)
        return {"code": 0, "data": {key: {"day": []}}}
    monkeypatch.setattr(snap, "_tx_kline_page", fake_page)
    rows = _us_klines_tencent("XYZ", "106.XYZ", days=20)   # 前缀映射.N拿不到→轮试.OQ
    assert len(rows) == 20


def test_fetch_klines_us_falls_back_to_tencent(monkeypatch):
    class FakeAk:
        def stock_us_hist(self, **kw):
            raise RuntimeError("RemoteDisconnected")
    monkeypatch.setitem(__import__("sys").modules, "akshare", FakeAk())
    monkeypatch.setattr(snap, "_tx_kline_page",
                        lambda param: _tx_payload("usABG.N"))
    rows = fetch_klines("ABG", "us", days=60, secid="106.ABG")
    assert len(rows) == 60 and rows[0]["close"] is not None
