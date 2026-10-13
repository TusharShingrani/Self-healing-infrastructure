"""The K in MAPE-K: what the loop remembers, and what it does with it.

Two jobs:

  recall()  given a symptom set seen before, return the cause that turned out
            to be right. This makes the second occurrence faster.

  prevention_rules()  the learned part. When an incident is closed, the loop
            records the symptoms that were present BEFORE the failure. If the
            same early symptoms appear again, it acts then instead of waiting
            for the failure. This is the immune memory idea: the first
            exposure is slow, later ones are handled before you notice.

Everything is written to SQLite so the incident history survives a restart
and can be exported as evidence.
"""

import json
import sqlite3
import time


SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    opened_at     REAL,
    closed_at     REAL,
    symptoms      TEXT,
    early_signs   TEXT,
    cause         TEXT,
    source        TEXT,
    actions       TEXT,
    outcome       TEXT,
    ticks_to_fix  INTEGER
);
CREATE TABLE IF NOT EXISTS prevention (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    early_signs TEXT UNIQUE,
    cause       TEXT,
    actions     TEXT,
    approved    INTEGER DEFAULT 0,
    created_at  REAL
);
"""


class Knowledge:
    def __init__(self, path=":memory:", auto_approve=True):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        # In a regulated setting a learned rule needs human sign-off before it
        # can act. auto_approve=False reproduces that, and the loop will then
        # only propose the rule and escalate.
        self.auto_approve = auto_approve

    # ---------- recall ----------

    def recall(self, symptoms):
        key = json.dumps(sorted(symptoms))
        row = self.db.execute(
            "SELECT cause, actions FROM incidents "
            "WHERE symptoms = ? AND outcome = 'resolved' "
            "ORDER BY id DESC LIMIT 1", (key,)
        ).fetchone()
        return dict(row) if row else None

    # ---------- record ----------

    def record(self, symptoms, early_signs, cause, source, actions, outcome, ticks):
        self.db.execute(
            "INSERT INTO incidents (opened_at, closed_at, symptoms, early_signs,"
            " cause, source, actions, outcome, ticks_to_fix)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (time.time(), time.time(), json.dumps(sorted(symptoms)),
             json.dumps(sorted(early_signs)), cause, source,
             json.dumps(actions), outcome, ticks),
        )
        self.db.commit()
        if outcome == "resolved" and early_signs:
            self._learn(early_signs, cause, actions)

    # ---------- learn ----------

    def _learn(self, early_signs, cause, actions):
        """Turn a resolved incident into a prevention rule.

        The actions are filtered: a prevention rule should fix the cause, not
        restart a service that has not failed yet.
        """
        preventive = [a for a in actions if a != "restart_service"]
        if not preventive:
            return
        self.db.execute(
            "INSERT OR IGNORE INTO prevention (early_signs, cause, actions,"
            " approved, created_at) VALUES (?,?,?,?,?)",
            (json.dumps(sorted(early_signs)), cause, json.dumps(preventive),
             1 if self.auto_approve else 0, time.time()),
        )
        self.db.commit()

    def prevention_match(self, symptoms):
        """Does a learned, approved rule cover these early symptoms?"""
        symptom_set = set(symptoms)
        for row in self.db.execute(
            "SELECT early_signs, cause, actions FROM prevention WHERE approved = 1"
        ):
            signs = set(json.loads(row["early_signs"]))
            if signs and signs <= symptom_set:
                return {"cause": row["cause"], "actions": json.loads(row["actions"])}
        return None

    def pending_rules(self):
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM prevention WHERE approved = 0")]

    def incidents(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM incidents")]
