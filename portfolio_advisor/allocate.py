from __future__ import annotations

def _rank_key(c):
    h = c.get("health_score")
    return c["score"] * ((h / 100) if h is not None else 0.8)

def allocate(candidates, capital, profile, cfg) -> dict:
    prof = cfg["advisor"]["risk_profiles"][profile]
    max_pos = prof["max_pos"] * capital
    max_ind = prof["max_industry"] * capital
    invest_budget = capital * (1 - prof["min_cash"])
    pool = [c for c in candidates
            if c.get("buy") and c["buy"].get("position_hint") != "观望"
            and c.get("price")]
    pool.sort(key=_rank_key, reverse=True)
    picks, by_ind, used = [], {}, 0.0
    for c in pool:
        if len(picks) >= prof["n_picks"] or used >= invest_budget - 1:
            break
        ind = c.get("industry") or "未知"
        room = min(max_pos, invest_budget - used, max_ind - by_ind.get(ind, 0.0))
        if room <= 0:
            continue
        if c["market"] == "a":
            lots = int(room // (c["price"] * 100))
            if lots < 1:
                continue                      # 买不起一手 → 顺位递补
            shares, amount = lots * 100, lots * 100 * c["price"]
        else:
            shares, amount = None, round(room, 2)
        picks.append({"code": c["code"], "name": c.get("name"),
                      "amount": round(amount, 2),
                      "weight": round(amount / capital * 100, 1),
                      "shares": shares,
                      "first_batch": round(amount * 0.6, 2),
                      "add_batch": round(amount * 0.4, 2),
                      "buy": c["buy"]})
        by_ind[ind] = by_ind.get(ind, 0.0) + amount
        used += amount
    return {"picks": picks, "cash_reserve": round(capital - used, 2),
            "cash_pct": round((capital - used) / capital * 100, 1)}
