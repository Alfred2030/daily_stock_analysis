from screener.norm import normalize_row, to_float

def test_to_float_handles_junk():
    assert to_float("1,234.5") == 1234.5
    assert to_float("-") is None
    assert to_float(None) is None
    assert to_float("") is None
    assert to_float(3.14) == 3.14

def test_normalize_a_share_row():
    row = {"代码": "600519", "名称": "贵州茅台", "最新价": "1450.0", "涨跌幅": "1.2",
           "成交额": "5600000000", "量比": "1.1", "换手率": "0.3",
           "市盈率-动态": "22.5", "市净率": "7.8", "总市值": "1820000000000",
           "流通市值": "1820000000000", "60日涨跌幅": "5.5"}
    r = normalize_row(row, "a")
    assert r["code"] == "600519" and r["market"] == "a"
    assert r["pe"] == 22.5 and r["turnover_amt"] == 5.6e9
    assert r["listing_days"] is None  # 快照没有上市天数，后续补

def test_normalize_us_row_strips_prefix():
    row = {"代码": "105.AAPL", "名称": "苹果", "最新价": "228.1", "涨跌幅": "-0.4",
           "成交额": "8100000000", "市盈率": "34.2"}
    r = normalize_row(row, "us")
    assert r["code"] == "AAPL" and r["pe"] == 34.2
    assert r["pb"] is None  # 美股快照无市净率 → None 不臆造
