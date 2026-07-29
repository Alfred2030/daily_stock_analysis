from __future__ import annotations
import html as _html
from pathlib import Path
from .wecom import DISCLAIMER

_CSS = ("body{font-family:system-ui;max-width:1080px;margin:24px auto;padding:0 16px;"
        "background:#0f1115;color:#e6e6e6}table{border-collapse:collapse;width:100%;"
        "margin:12px 0}td,th{border:1px solid #333;padding:6px 10px;font-size:14px}"
        "th{background:#1a1d24}h1,h2{color:#e8c66a}.card{background:#1a1d24;"
        "border-radius:10px;padding:14px;margin:10px 0}.flag{color:#ff7a6b}"
        ".dis{color:#888;font-size:12px;margin-top:28px}")
INDEX_KEEP = 60  # 每日2份(A股+美股)×30天

def _esc(v):
    return _html.escape(str(v)) if v is not None else "—"

def _fin_block(code, fmap):
    f = (fmap or {}).get(code)
    if not f:
        return "<p>财务数据不足</p>"
    h = f.get("health") or {}
    flags = "".join(f'<div class="flag">⚠ {_esc(x)}</div>' for x in h.get("flags", []))
    return (f'<p>财务健康分：<b>{_esc(h.get("score"))}</b>'
            f'（覆盖率 {_esc(h.get("coverage"))}）</p>{flags}'
            f'<p>{_esc(f.get("analysis_text") or "AI 分析暂缺")}</p>'
            f'<p><i>{_esc(f.get("outlook_text") or "")}</i></p>')

def write_html_report(out_dir, market, day, top, finance_map, alloc,
                      advisor_text, intel) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mkt = "A股" if market == "a" else "美股"
    rows = ""
    for r in top:
        b = r.get("buy") or {}
        rows += (f"<tr><td>{_esc(r['code'])}</td><td>{_esc(r['name'])}"
                 f"{'（' + _esc('/'.join(r['tags'])) + '）' if r.get('tags') else ''}</td>"
                 f"<td>{_esc(r['score'])}</td><td>{_esc(r.get('industry'))}</td>"
                 f"<td>{_esc(b.get('buy_low'))}~{_esc(b.get('buy_high'))}</td>"
                 f"<td>{_esc(b.get('position_hint'))}</td></tr>")
    cards = "".join(f'<div class="card"><h3>{_esc(r["name"])}（{_esc(r["code"])}）</h3>'
                    f'{_fin_block(r["code"], finance_map)}</div>' for r in top)
    strat = ""
    if alloc and alloc.get("picks"):
        srows = "".join(f"<tr><td>{_esc(p['name'])}</td><td>{p['amount']}</td>"
                        f"<td>{p['weight']}%</td><td>{_esc(p['shares'])}</td>"
                        f"<td>{p['first_batch']} / {p['add_batch']}</td></tr>"
                        for p in alloc["picks"])
        strat = (f"<h2>今日策略建议</h2><table><tr><th>股票</th><th>金额</th>"
                 f"<th>占比</th><th>股数</th><th>首建/加仓</th></tr>{srows}</table>"
                 f"<p>现金保留：{alloc['cash_pct']}%</p><p>{_esc(advisor_text or '')}</p>")
    intel_html = "".join(f'<div class="card"><b>{_esc(ind)}</b>'
                         f"<p>{_esc(v.get('assessment') or '暂缺')}</p></div>"
                         for ind, v in (intel or {}).items())
    page = (f"<!doctype html><meta charset='utf-8'><title>{mkt} {day} 选股日报</title>"
            f"<style>{_CSS}</style><h1>Cxodex 选股神器 · {mkt} {day}</h1>"
            f"<h2>今日新面孔 Top{len(top)}</h2><table><tr><th>代码</th><th>名称</th>"
            f"<th>综合分</th><th>行业</th><th>买入区间</th><th>仓位提示</th></tr>"
            f"{rows}</table>{strat}<h2>行业情报</h2>{intel_html}"
            f"<h2>个股财务分析（IMDS）</h2>{cards}"
            f"<p class='dis'>{DISCLAIMER}</p>")
    path = out / f"{day}-{market}.html"
    path.write_text(page, encoding="utf-8")
    items = sorted(out.glob("*-*.html"), reverse=True)[:INDEX_KEEP]
    idx = "".join(f'<li><a href="{p.name}">{p.stem}</a></li>'
                  for p in items if p.name != "index.html")
    (out / "index.html").write_text(
        f"<!doctype html><meta charset='utf-8'><title>选股日报</title>"
        f"<style>{_CSS}</style><h1>Cxodex 选股神器 · 历史日报</h1><ul>{idx}</ul>",
        encoding="utf-8")
    return path
