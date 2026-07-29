from __future__ import annotations
import json
from .ratios import peer_card, mgmt_card, risk_card
from .scoring import health_score
from sgod.llm import chat

_SYSTEM = ("你是一名资深财务顾问，使用 IMDS 财务管理方法论（同行对比、管理层视角、"
           "风险扫描三张卡）解读上市公司财务。只依据给出的数据陈述，缺失的数据明确说"
           "「数据不足」，不得编造数字。")

def build_prompt(code, name, market, series, industry=None, peer_median=None) -> str:
    peer, mgmt, risk = peer_card(series), mgmt_card(series), risk_card(series)
    health = health_score(peer, mgmt, risk, peer_median)
    mkt = "A股" if market == "a" else "美股"
    return (
        f"{mkt}公司：{name}（{code}），行业：{industry or '未知'}。\n"
        f"同行对比卡（毛利率/净利率/ROE为百分数，周转率为倍数）：{json.dumps(peer, ensure_ascii=False)}\n"
        f"管理层视角卡：{json.dumps(mgmt, ensure_ascii=False)}\n"
        f"风险扫描卡：{json.dumps(risk, ensure_ascii=False)}\n"
        f"财务健康评分：{json.dumps(health, ensure_ascii=False)}\n"
        f"同行中位数（可能为空）：{json.dumps(peer_median, ensure_ascii=False)}\n\n"
        "请输出两节，用「### 管理层分析和关注」「### 财务展望」作小标题：\n"
        "1) 管理层分析和关注：当期盈利质量、费用结构、现金流与风险点，150字内；\n"
        "2) 财务展望：基于增速/毛利率方向/现金流走向对未来2-4个季度给出"
        "改善/恶化/平稳判断与2个关键观察指标，120字内。")

def _split_sections(text):
    if not text:
        return None, None
    a, o = None, None
    if "### 财务展望" in text:
        head, o = text.split("### 财务展望", 1)
        a = head.replace("### 管理层分析和关注", "").strip() or None
        o = o.strip() or None
    else:
        a = text.strip() or None
    return a, o

def finance_report(code, name, market, series, industry=None, peer_median=None):
    peer, mgmt, risk = peer_card(series), mgmt_card(series), risk_card(series)
    health = health_score(peer, mgmt, risk, peer_median)
    text = chat(build_prompt(code, name, market, series, industry, peer_median),
                system=_SYSTEM) if series else None
    analysis, outlook = _split_sections(text)
    return {"cards": {"peer": peer, "mgmt": mgmt, "risk": risk},
            "health": health, "analysis_text": analysis, "outlook_text": outlook}
