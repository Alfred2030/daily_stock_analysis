from __future__ import annotations
import sqlite3
from datetime import date, timedelta
from pathlib import Path

class RecommendHistory:
    def __init__(self, db_path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS recommend_history ("
            "market TEXT NOT NULL, code TEXT NOT NULL, day TEXT NOT NULL,"
            "PRIMARY KEY (market, code, day))")
        self.conn.commit()

    def recent_codes(self, market: str, days: int) -> set:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        rows = self.conn.execute(
            "SELECT code FROM recommend_history WHERE market=? AND day>=?",
            (market, cutoff)).fetchall()
        return {r[0] for r in rows}

    def record(self, market: str, codes, day: str) -> None:
        self.conn.executemany(
            "INSERT OR IGNORE INTO recommend_history VALUES (?,?,?)",
            [(market, c, day) for c in codes])
        self.conn.commit()
