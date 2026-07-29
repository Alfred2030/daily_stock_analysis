from __future__ import annotations
import os
import requests
from sgod.llm import chat

def build_queries(industry, market):
    if market == "a":
        return [f"{industry} 行业政策 最新", f"{industry} 产业数据 出口 贸易"]
    return [f"{industry} 美联储 关税 政策 影响", f"{industry} CPI 监管 动态"]

def _search(query):
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return []
    try:
        resp = requests.post("https://api.tavily.com/search",
                             json={"api_key": key, "query": query,
                                   "max_results": 5, "days": 7},
                             timeout=30)
        resp.raise_for_status()
        return [r.get("title", "") for r in resp.json().get("results", []) if r.get("title")]
    except requests.RequestException:
        return []

def build_intel_prompt(industry, news, stocks):
    lines = "\n".join(f"- {n}" for n in news) or "（无新闻，仅按常识性宏观背景判断，明确标注不确定性）"
    return (f"行业：{industry}。近7天相关新闻标题：\n{lines}\n"
            f"该行业候选股：{', '.join(stocks)}。\n"
            "请判断：1) 总体利好/利空/中性；2) 影响时间窗（如1-2月/一季度）；"
            "3) 对候选股的影响一句话。共80字内，以「利好：/利空：/中性：」开头。")

def gather_intel(candidates, market):
    groups = {}
    for c in candidates:
        ind = c.get("industry") or "未知行业"
        groups.setdefault(ind, []).append(c["code"])
    out = {}
    for ind, codes in groups.items():
        news = []
        for q in build_queries(ind, market):
            news.extend(_search(q))
        news = news[:8]
        assessment = chat(build_intel_prompt(ind, news, codes))
        out[ind] = {"stocks": codes, "news": news, "assessment": assessment}
    return out
