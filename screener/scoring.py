# screener/scoring.py
# 三维打分：每维 0-100，缺数据记 50（中性）。分段线性打分，阈值就近取材于
# A股/美股常识区间；细调只改这里的表，不改结构。
from __future__ import annotations

def _piecewise(v, points):
    """points: [(x0,y0),(x1,y1),...] 单调 x；v 超界取端点分。v=None → None"""
    if v is None:
        return None
    pts = sorted(points)
    if v <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if v <= x1:
            return y0 + (y1 - y0) * (v - x0) / (x1 - x0)
    return pts[-1][1]

def _avg(vals):
    vs = [v for v in vals if v is not None]
    return sum(vs) / len(vs) if vs else None

def _finance_score(r):
    pe = _piecewise(r.get("pe"), [(5, 90), (15, 100), (30, 70), (60, 40), (120, 10)])
    pb = _piecewise(r.get("pb"), [(0.5, 80), (1.5, 100), (5, 60), (15, 20)])
    return _avg([pe, pb])

def _technical_score(r):
    mom = _piecewise(r.get("pct_60d"), [(-30, 10), (-5, 40), (5, 70), (25, 100), (60, 60)])
    chg = _piecewise(r.get("pct_chg"), [(-9, 20), (0, 60), (4, 100), (9, 50)])
    return _avg([mom, chg])

def _flow_score(r):
    vr = _piecewise(r.get("volume_ratio"), [(0.3, 20), (1.0, 60), (2.0, 100), (5.0, 40)])
    tr = _piecewise(r.get("turnover_rate"), [(0.2, 30), (2, 80), (7, 100), (20, 30)])
    return _avg([vr, tr])

def score_row(row: dict, cfg: dict) -> dict:
    parts = {"finance": _finance_score(row), "technical": _technical_score(row),
             "flow": _flow_score(row)}
    parts = {k: (50.0 if v is None else round(v, 1)) for k, v in parts.items()}
    w = cfg["scoring"]["weights"]
    score = sum(parts[k] * w[k] for k in parts)
    return {**row, "score": round(score, 1), "score_parts": parts}

def rank_top(rows, cfg, exclude_codes=frozenset()):
    pool = [r for r in rows if r["code"] not in exclude_codes]
    pool.sort(key=lambda r: r["score"], reverse=True)
    return pool[: cfg["screener"]["top_n"]]
