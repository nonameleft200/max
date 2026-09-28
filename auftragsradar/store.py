"""SQLite-Ablage, damit Folgeläufe nur Neues melden und Anreicherungen nicht doppelt laufen."""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from .models import Notice

SCHEMA = """
CREATE TABLE IF NOT EXISTS notices (
  id TEXT PRIMARY KEY, source TEXT, kind TEXT, title TEXT, description TEXT, buyer TEXT,
  region TEXT, locality TEXT, cpv TEXT, procedure TEXT, regime TEXT, value REAL,
  published TEXT, deadline TEXT, url TEXT, supplier TEXT, raw_id TEXT,
  score INTEGER DEFAULT 0, reasons TEXT DEFAULT '', excluded INTEGER DEFAULT 0,
  first_seen TEXT, last_seen TEXT, enriched INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_notices_score ON notices(score);
CREATE INDEX IF NOT EXISTS idx_notices_kind ON notices(kind);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def upsert(self, n: Notice, score: int, reasons: str, excluded: bool) -> bool:
        """Speichert eine Bekanntmachung. Gibt True zurück, wenn sie neu ist."""
        today = date.today().isoformat()
        row = self.db.execute("SELECT id, deadline, cpv, enriched FROM notices WHERE id=?", (n.id,)).fetchone()
        d = n.to_row()
        if row:
            # bereits angereicherte Felder nicht überschreiben
            deadline = n.deadline or row["deadline"]
            cpv = d["cpv"] or row["cpv"]
            self.db.execute(
                """UPDATE notices SET title=?, description=?, buyer=?, region=?, locality=?, cpv=?, procedure=?,
                   regime=?, value=?, published=?, deadline=?, url=?, supplier=?, score=?, reasons=?, excluded=?, last_seen=?
                   WHERE id=?""",
                (d["title"], d["description"], d["buyer"], d["region"], d["locality"], cpv, d["procedure"],
                 d["regime"], d["value"], d["published"], deadline, d["url"], d["supplier"], score, reasons,
                 int(excluded), today, n.id))
            return False
        self.db.execute(
            """INSERT INTO notices (id, source, kind, title, description, buyer, region, locality, cpv, procedure,
               regime, value, published, deadline, url, supplier, raw_id, score, reasons, excluded, first_seen, last_seen)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (n.id, d["source"], d["kind"], d["title"], d["description"], d["buyer"], d["region"], d["locality"],
             d["cpv"], d["procedure"], d["regime"], d["value"], d["published"], d["deadline"], d["url"],
             d["supplier"], d["raw_id"], score, reasons, int(excluded), today, today))
        return True

    def set_enriched(self, n: Notice) -> None:
        self.db.execute("UPDATE notices SET deadline=?, cpv=?, procedure=?, regime=?, url=?, description=?, enriched=1 WHERE id=?",
                        (n.deadline, ",".join(n.cpv), n.procedure, n.regime, n.url, n.description, n.id))

    def candidates(self, min_score: int, kind: str = "tender", only_new: bool = False) -> list[sqlite3.Row]:
        q = "SELECT * FROM notices WHERE excluded=0 AND kind=? AND score>=?"
        args: list = [kind, min_score]
        if only_new:
            q += " AND first_seen=?"
            args.append(date.today().isoformat())
        q += " ORDER BY score DESC, published DESC"
        return self.db.execute(q, args).fetchall()

    def unenriched(self, min_score: int) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM notices WHERE excluded=0 AND kind='tender' AND score>=? AND enriched=0 ORDER BY score DESC",
            (min_score,)).fetchall()

    def awards(self, min_score: int) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM notices WHERE excluded=0 AND kind='award' AND score>=? ORDER BY published DESC",
            (min_score,)).fetchall()

    def commit(self) -> None:
        self.db.commit()
