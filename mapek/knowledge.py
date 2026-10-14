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
CREATE TABLE IF NOT EXISTS advice (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  REAL,
    target      TEXT,
    reason      TEXT,
    symptoms    TEXT,
    cause       TEXT,
    actions     TEXT,
    explanation TEXT,
    human_checks TEXT,
    risk        TEXT,
    model       TEXT,
    status      TEXT,          -- requested | pending | approved | rejected | failed
    decided_by  TEXT,
    decided_at  REAL
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
        # check_same_thread=False: the advisor writes its answer from a worker
        # thread. SQLite serialises the writes; every write commits at once.
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=10)
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

    # ---------- advice (human in the loop) ----------
    #
    # The advisor only ever writes here. Advice becomes usable by the loop
    # only after a person approves it, and even then only as a diagnosis whose
    # actions come from the fixed catalogue and still pass the guardrails and
    # the high-risk approval gate.

    def open_advice(self, target, reason, symptoms):
        """Record a request, or return None if the same one is already open."""
        key = json.dumps(sorted(symptoms))
        row = self.db.execute(
            "SELECT id FROM advice WHERE target = ? AND symptoms = ? AND reason = ?"
            " AND status IN ('requested', 'pending')", (target, key, reason)).fetchone()
        if row:
            return None
        cur = self.db.execute(
            "INSERT INTO advice (created_at, target, reason, symptoms, status)"
            " VALUES (?,?,?,?, 'requested')", (time.time(), target, reason, key))
        self.db.commit()
        return cur.lastrowid

    def complete_advice(self, advice_id, cause, actions, explanation,
                        human_checks, risk, model, status="pending"):
        self.db.execute(
            "UPDATE advice SET cause=?, actions=?, explanation=?, human_checks=?,"
            " risk=?, model=?, status=? WHERE id=? AND status='requested'",
            (cause, json.dumps(actions), explanation, json.dumps(human_checks),
             risk, model, status, advice_id))
        self.db.commit()

    def expire_advice(self, max_age=120, now=None):
        """A lost worker must not leave the same request deduplicated forever."""
        now = time.time() if now is None else now
        cur = self.db.execute(
            "UPDATE advice SET status='failed',explanation=? WHERE status='requested' AND created_at<?",
            ('No completed response within the request lease; retry or investigate manually', now-max_age))
        self.db.commit()
        return cur.rowcount

    def decide_advice(self, advice_id, approve, who="human"):
        cur = self.db.execute(
            "UPDATE advice SET status=?, decided_by=?, decided_at=?"
            " WHERE id=? AND status='pending'",
            ("approved" if approve else "rejected", who, time.time(), advice_id))
        self.db.commit()
        return cur.rowcount == 1

    def approved_advice(self, symptoms):
        """Approved advice whose symptom set is fully present, newest first."""
        symptom_set = set(symptoms)
        for row in self.db.execute(
            "SELECT * FROM advice WHERE status='approved' ORDER BY id DESC"):
            signs = set(json.loads(row["symptoms"]))
            actions = json.loads(row["actions"] or "[]")
            if signs and signs <= symptom_set and actions:
                return {"id": row["id"], "cause": row["cause"], "actions": actions}
        return None

    def advice(self, status=None):
        if status:
            rows = self.db.execute("SELECT * FROM advice WHERE status=? ORDER BY id",
                                   (status,))
        else:
            rows = self.db.execute("SELECT * FROM advice ORDER BY id")
        return [dict(r) for r in rows]

    def approve_rule(self, rule_id):
        cur = self.db.execute("UPDATE prevention SET approved=1 WHERE id=?", (rule_id,))
        self.db.commit()
        return cur.rowcount == 1

    def rules(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM prevention ORDER BY id")]

    def counts(self):
        incidents = dict(self.db.execute(
            "SELECT outcome, COUNT(*) FROM incidents GROUP BY outcome").fetchall())
        rules = dict(self.db.execute(
            "SELECT approved, COUNT(*) FROM prevention GROUP BY approved").fetchall())
        advice = dict(self.db.execute(
            "SELECT status, COUNT(*) FROM advice GROUP BY status").fetchall())
        return {"incidents": incidents,
                "rules": {"true": rules.get(1, 0), "false": rules.get(0, 0)},
                "advice": advice}
