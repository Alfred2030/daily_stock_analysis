from __future__ import annotations
import json
from sgod.llm import chat

def build_advisor_prompt(alloc, market):
    mkt = "A股" if market == "a" else "美股"
    return (f"{mkt}今日建议组合：{json.dumps(alloc, ensure_ascii=False)}\n"
            "请用200字内说明：1) 组合逻辑（为何这样分散与配比）；"
            "2) 主要风险；3) 止损与调仓条件（跌破支撑位/基本面恶化等）。"
            "语气克制专业，明确这是研究参考非投资建议。")

def advisor_report(alloc, market):
    if not alloc.get("picks"):
        return None
    return chat(build_advisor_prompt(alloc, market))
