from __future__ import annotations
import os
import requests

DISCLAIMER = "本报告由 AI 生成，仅供研究参考，不构成投资建议，据此操作风险自负"
_LIMIT = 4000

def _top5_lines(top):
    lines = []
    for r in top[:5]:
        b = r.get("buy") or {}
        tag = f"[{'/'.join(r['tags'])}]" if r.get("tags") else ""
        h = r.get("health_score")
        lines.append(
            f"**{r['name']}({r['code']})**{tag} 分{r['score']}"
            f"{f' 财务{h}' if h is not None else ''}\n"
            f"> 买点 {b.get('buy_low')}~{b.get('buy_high')} {b.get('position_hint', '')}"
            f"｜{b.get('trigger', '')}")
    return lines

def build_daily_markdown(market, day, top, alloc, advisor_text, intel, web_url):
    mkt = "A股" if market == "a" else "美股"
    head = f"# 📈 Cxodex 选股神器 · {mkt} {day}\n共筛出 {len(top)} 只新面孔，Top5：\n"
    picks = "\n".join(_top5_lines(top))
    strat = ""
    if alloc and alloc.get("picks"):
        rows = "、".join(f"{p['name']} {p['weight']}%" for p in alloc["picks"])
        strat = (f"\n## 今日策略建议\n{rows}｜现金 {alloc['cash_pct']}%\n"
                 + (advisor_text or ""))
    intel_txt = "\n## 行业情报\n" + "\n".join(
        f"- **{ind}**：{v['assessment']}" for ind, v in (intel or {}).items()
        if v.get("assessment"))
    tail = f"\n\n[完整报告]({web_url})\n> {DISCLAIMER}"
    for parts in ((head, picks, strat, intel_txt),   # 全量
                  (head, picks, strat, ""),          # 砍情报
                  (head, picks, "", "")):            # 砍策略
        md = "".join(parts) + tail
        if len(md.encode("utf-8")) <= _LIMIT:
            return md
    return (head + tail)[: _LIMIT]

def send_wecom(markdown: str) -> bool:
    url = os.getenv("SGOD_WECOM_WEBHOOK")
    if not url:
        return False
    try:
        resp = requests.post(url, json={"msgtype": "markdown",
                                        "markdown": {"content": markdown}},
                             timeout=15)
        return resp.status_code == 200 and resp.json().get("errcode") == 0
    except requests.RequestException:
        return False
