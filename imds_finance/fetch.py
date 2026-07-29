# 财报适配器：A股走 eastmoney 个股三大报表（利润表/资产负债表/现金流量表），
# 美股走 yfinance 三表。列名/科目名全部走同义词映射，映射不到→None；整体失败→[]。
#
# A股口径注意：利润表/现金流量表的科目是"本年累计"（YTD），必须按报告期月份
# 反推为单季度数（Q1=累计值本身，Qn=累计值-上一季度累计值，每年 1 月重置）；
# 资产负债表科目是时点数，不做反算。
from __future__ import annotations
from screener.norm import to_float

# 字段名 → eastmoney 列名（利润表 stock_profit_sheet_by_report_em）
_EM_INCOME_COLS = {
    "revenue": "TOTAL_OPERATE_INCOME",
    "net_profit": "PARENT_NETPROFIT",
    "sales_exp": "SALE_EXPENSE",
    "admin_exp": "MANAGE_EXPENSE",
    "fin_exp": "FINANCE_EXPENSE",
    "rd_exp": "RESEARCH_EXPENSE",
}
_EM_OPERATE_COST_COL = "OPERATE_COST"          # 营业成本，用于反算毛利润
# 字段名 → eastmoney 列名（现金流量表 stock_cash_flow_sheet_by_report_em）
_EM_CASH_COLS = {
    "op_cashflow": "NETCASH_OPERATE",
}
# 字段名 → eastmoney 列名（资产负债表 stock_balance_sheet_by_report_em，时点数不反算）
_EM_BALANCE_COLS = {
    "total_assets": "TOTAL_ASSETS",
    "total_liab": "TOTAL_LIABILITIES",
    "equity": "TOTAL_PARENT_EQUITY",
    "ar": "ACCOUNTS_RECE",
    "inventory": "INVENTORY",
    "goodwill": "GOODWILL",
    "current_assets": "TOTAL_CURRENT_ASSETS",
    "current_liab": "TOTAL_CURRENT_LIAB",
}
_EM_DATE_COL = "REPORT_DATE"

_US_SYNONYMS = {
    "revenue": ["Total Revenue"], "net_profit": ["Net Income"],
    "gross_profit": ["Gross Profit"],
    "op_cashflow": ["Operating Cash Flow", "Total Cash From Operating Activities"],
    "total_assets": ["Total Assets"],
    "total_liab": ["Total Liabilities Net Minority Interest", "Total Liab"],
    "equity": ["Stockholders Equity", "Total Stockholder Equity"],
    "ar": ["Accounts Receivable"], "inventory": ["Inventory"],
    "goodwill": ["Goodwill"], "current_assets": ["Current Assets"],
    "current_liab": ["Current Liabilities"],
    "sales_exp": [], "admin_exp": ["Selling General And Administration"],
    "fin_exp": ["Interest Expense"], "rd_exp": ["Research And Development"],
}
_FIELDS = ["revenue", "net_profit", "gross_profit", "op_cashflow", "total_assets",
           "total_liab", "equity", "ar", "inventory", "goodwill", "current_assets",
           "current_liab", "sales_exp", "admin_exp", "fin_exp", "rd_exp"]

def _em_symbol(code):
    """6 位代码 → eastmoney 交易所前缀：6xx → SH，0xx/3xx → SZ。"""
    c = str(code).strip()
    return f"{'SH' if c.startswith('6') else 'SZ'}{c}"

def _em_statements(code):
    """monkeypatch 用的唯一网络接缝：三张表一次性拉回。"""
    import akshare as ak
    symbol = _em_symbol(code)
    profit = ak.stock_profit_sheet_by_report_em(symbol=symbol)
    balance = ak.stock_balance_sheet_by_report_em(symbol=symbol)
    cash = ak.stock_cash_flow_sheet_by_report_em(symbol=symbol)
    return profit, balance, cash

def _yf_frames(code):
    import yfinance as yf
    t = yf.Ticker(code)
    return t.quarterly_financials, t.quarterly_balance_sheet, t.quarterly_cashflow

def _period_str(raw):
    return str(raw)[:10]

def _quarter_of(period):
    return {"03": 1, "06": 2, "09": 3, "12": 4}.get(period[5:7])

def _decumulate_column(df, value_col):
    """本年累计值 → 单季度值，按自然年重置。返回 {period_str: 单季度值 or None}。"""
    out = {}
    if df is None or getattr(df, "empty", True) or value_col not in getattr(df, "columns", []):
        return out
    rows = []
    for _, row in df.iterrows():
        period = _period_str(row.get(_EM_DATE_COL))
        q = _quarter_of(period)
        if q is None:
            continue
        rows.append((period, int(period[:4]), q, to_float(row.get(value_col))))
    rows.sort(key=lambda x: x[0])                       # 旧→新，便于按年累加反算
    prev_cum = {}
    for period, year, q, cum in rows:
        if cum is None:
            out[period] = None
        elif q == 1:
            out[period] = cum
        else:
            prev = prev_cum.get(year)
            out[period] = round(cum - prev, 6) if prev is not None else None
        if cum is not None:
            prev_cum[year] = cum
    return out

def _point_in_time_column(df, value_col):
    out = {}
    if df is None or getattr(df, "empty", True) or value_col not in getattr(df, "columns", []):
        return out
    for _, row in df.iterrows():
        out[_period_str(row.get(_EM_DATE_COL))] = to_float(row.get(value_col))
    return out

def _a_series(code, quarters=8):
    profit, balance, cash = _em_statements(code)
    income_q = {k: _decumulate_column(profit, col) for k, col in _EM_INCOME_COLS.items()}
    cost_q = _decumulate_column(profit, _EM_OPERATE_COST_COL)
    cash_q = {k: _decumulate_column(cash, col) for k, col in _EM_CASH_COLS.items()}
    balance_pit = {k: _point_in_time_column(balance, col) for k, col in _EM_BALANCE_COLS.items()}

    periods = set()
    for d in list(income_q.values()) + [cost_q] + list(cash_q.values()) + list(balance_pit.values()):
        periods |= set(d.keys())
    periods = sorted(periods)[-quarters:]                # 旧→新，取最近 N 季

    series = []
    for p in periods:
        rec = {"period": p}
        for k, d in income_q.items():
            rec[k] = d.get(p)
        for k, d in cash_q.items():
            rec[k] = d.get(p)
        for k, d in balance_pit.items():
            rec[k] = d.get(p)
        rev, cost = rec.get("revenue"), cost_q.get(p)
        rec["gross_profit"] = round(rev - cost, 6) if (rev is not None and cost is not None) else None
        series.append(rec)
    return series

def _us_series(code, quarters=8):
    fin, bal, cf = _yf_frames(code)
    frames = {"fin": fin, "bal": bal, "cf": cf}
    cols = sorted({c for f in frames.values() for c in getattr(f, "columns", [])})
    cols = cols[-quarters:]
    def _val(key, col):
        for f in frames.values():
            for syn in _US_SYNONYMS[key]:
                if syn in getattr(f, "index", []) and col in f.columns:
                    return to_float(f.at[syn, col])
        return None
    return [{"period": str(c.date()) if callable(getattr(c, "date", None)) else str(c),
             **{k: _val(k, c) for k in _FIELDS}} for c in cols]

def fetch_series(code, market, quarters=8):
    try:
        return (_a_series if market == "a" else _us_series)(code, quarters)
    except Exception:
        return []

def fetch_industry(code, market):
    try:
        if market == "a":
            import akshare as ak
            info = ak.stock_individual_info_em(symbol=code)
            kv = dict(zip(info["item"], info["value"]))
            ind = kv.get("行业")
            return str(ind) if ind else None
        import yfinance as yf
        return yf.Ticker(code).info.get("sector")
    except Exception:
        return None

def fetch_peer_median(industry, market):
    if market != "a" or not industry:
        return None                     # 美股首版无同行中位数，不臆造
    try:
        import akshare as ak
        import statistics
        df = ak.stock_board_industry_cons_em(symbol=industry)
        def _med(col):
            vals = [to_float(v) for v in df.get(col, [])]
            vals = [v for v in vals if v is not None]
            return round(statistics.median(vals), 1) if len(vals) >= 5 else None
        return {"gross_margin": None, "net_margin": None,
                "roe": None, "debt_ratio": None,
                "pe_median": _med("市盈率-动态"), "pb_median": _med("市净率")}
    except Exception:
        return None
