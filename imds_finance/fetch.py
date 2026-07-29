# 财报适配器：A股走 akshare 财务摘要，美股走 yfinance 三表。
# 列名/科目名全部走同义词映射，映射不到→None；整体失败→[]。
from __future__ import annotations
from screener.norm import to_float

_A_SYNONYMS = {
    "revenue": ["营业总收入", "营业收入"],
    "net_profit": ["归母净利润", "净利润"],
    "gross_profit": ["毛利润", "毛利"],
    "op_cashflow": ["经营现金流量净额", "经营活动产生的现金流量净额"],
    "total_assets": ["总资产", "资产总计"],
    "total_liab": ["总负债", "负债合计"],
    "equity": ["股东权益合计", "归母股东权益", "所有者权益合计"],
    "ar": ["应收账款"],
    "inventory": ["存货"],
    "goodwill": ["商誉"],
    "current_assets": ["流动资产合计"],
    "current_liab": ["流动负债合计"],
    "sales_exp": ["销售费用"],
    "admin_exp": ["管理费用"],
    "fin_exp": ["财务费用"],
    "rd_exp": ["研发费用"],
}
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
_FIELDS = list(_A_SYNONYMS)

def _ak_financial_abstract(code):
    import akshare as ak
    return ak.stock_financial_abstract(symbol=code)

def _yf_frames(code):
    import yfinance as yf
    t = yf.Ticker(code)
    return t.quarterly_financials, t.quarterly_balance_sheet, t.quarterly_cashflow

def _a_series(code, quarters=8):
    df = _ak_financial_abstract(code)
    period_cols = [c for c in df.columns if str(c).isdigit() and len(str(c)) == 8]
    period_cols = sorted(period_cols)[-quarters:]
    by_indicator = {str(r["指标"]).strip(): r for _, r in df.iterrows()}
    def _val(key, col):
        for syn in _A_SYNONYMS[key]:
            if syn in by_indicator:
                return to_float(by_indicator[syn].get(col))
        return None
    return [{"period": str(c), **{k: _val(k, c) for k in _FIELDS}}
            for c in period_cols]

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
