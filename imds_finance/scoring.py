# imds_finance/scoring.py
# 财务健康评分：指标→0-100 分段线性，加权平均；coverage<0.4 不打分。
# 同行中位数存在时：核心盈利指标显著优于中位数各 +2.5、显著落后各 -2.5（毛利率与ROE两项）。
from __future__ import annotations
from screener.scoring import _piecewise  # 复用分段线性

_SPECS = [
    # (取值函数, 分段表, 权重)
    (lambda p, m, r: p.get("gross_margin"), [(5, 20), (20, 55), (40, 85), (60, 100)], 1.0),
    (lambda p, m, r: p.get("net_margin"),   [(0, 25), (8, 60), (20, 90), (35, 100)], 1.0),
    (lambda p, m, r: p.get("roe"),          [(2, 20), (8, 55), (15, 85), (25, 100)], 1.5),
    (lambda p, m, r: p.get("debt_ratio"),   [(20, 95), (45, 75), (65, 45), (85, 10)], 1.0),
    (lambda p, m, r: m.get("cash_quality"), [(0.2, 15), (0.7, 55), (1.0, 85), (1.5, 100)], 1.5),
    (lambda p, m, r: m.get("rev_yoy"),      [(-20, 15), (0, 50), (15, 80), (40, 100)], 1.0),
    (lambda p, m, r: m.get("profit_yoy"),   [(-30, 10), (0, 50), (20, 85), (50, 100)], 1.0),
    (lambda p, m, r: r.get("current_ratio"),[(0.6, 15), (1.0, 50), (1.8, 90), (3.0, 100)], 0.8),
    (lambda p, m, r: r.get("ar_vs_rev_gap"),[(-10, 100), (5, 80), (20, 40), (40, 5)], 0.8),
    (lambda p, m, r: r.get("goodwill_ratio"),[(5, 100), (20, 75), (40, 40), (60, 10)], 0.7),
]

_FLAG_RULES = [
    (lambda p, m, r: m.get("cash_quality") is not None and m.get("cash_quality") < 0.5,
     "经营现金流质量差（现金流/净利<0.5）"),
    (lambda p, m, r: r.get("ar_vs_rev_gap") is not None and r.get("ar_vs_rev_gap") > 15,
     "应收账款增速显著快于营收，回款风险"),
    (lambda p, m, r: r.get("inv_vs_rev_gap") is not None and r.get("inv_vs_rev_gap") > 15,
     "存货增速显著快于营收，滞销风险"),
    (lambda p, m, r: r.get("goodwill_ratio") is not None and r.get("goodwill_ratio") > 40,
     "商誉/净资产过高，减值风险"),
    (lambda p, m, r: p.get("debt_ratio") is not None and p.get("debt_ratio") > 75,
     "资产负债率过高"),
]

def health_score(peer, mgmt, risk, peer_median=None) -> dict:
    scored, weights = [], []
    for get, table, w in _SPECS:
        v = get(peer, mgmt, risk)
        s = _piecewise(v, table)
        if s is not None:
            scored.append(s * w)
            weights.append(w)
    coverage = round(len(weights) / len(_SPECS), 2)
    flags = [msg for cond, msg in _FLAG_RULES if cond(peer, mgmt, risk)]
    if coverage < 0.4:
        return {"score": None, "coverage": coverage, "flags": flags}
    score = sum(scored) / sum(weights)
    if peer_median:
        for key in ("gross_margin", "roe"):
            a, b = peer.get(key), peer_median.get(key)
            if a is not None and b is not None and b != 0:
                if a > b * 1.3:
                    score += 2.5
                elif a < b * 0.7:
                    score -= 2.5
    return {"score": round(max(0.0, min(100.0, score)), 1),
            "coverage": coverage, "flags": flags}
