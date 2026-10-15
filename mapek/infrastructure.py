"""Shared investigation and cause binding used by the job-service adapter.

The module name is retained to preserve imports; no DNS/Redis application or
legacy service controller is implemented here.
"""
import json
import re
from .operator import Operator, encode
from .stages import Diagnosis

class InvestigationOperator(Operator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db.execute('CREATE TABLE IF NOT EXISTS investigations(scope TEXT,symptoms TEXT,cause TEXT,actions TEXT,who TEXT,notes TEXT,UNIQUE(scope,symptoms))')

    def record_human(self, world, case_id, actions, who, notes):
        if any(not a.startswith('recipe_') or a[7:] not in world.recipes.recipes for a in actions):
            raise ValueError('Human infrastructure repairs must use this stack capability book')
        return super().record_human(world, case_id, actions, who, notes)

    def investigate(self, world, case_id, cause, actions, who, notes):
        case = self.case(case_id)
        if case['status'] != 'pending' or case['cause'] != 'unknown' or not who.strip() or not notes.strip() or not re.fullmatch('[a-z][a-z0-9_]{2,80}', cause) or cause == 'unknown':
            raise ValueError('Pending unknown incident, meaningful diagnosis and investigator required')
        if not actions or any(not a.startswith('recipe_') or a[7:] not in world.recipes.recipes for a in actions):
            raise ValueError('Only reviewed typed recipes may be bound to an investigation')
        obs = world.observe(False)
        from .stages import Monitor
        symptoms = Monitor().symptoms(obs)
        identity, scope = self.context(world, symptoms, 'unknown', [], obs)
        if identity != case['identity']:
            raise ValueError('Evidence changed during investigation; open the current incident')
        from .operator import redact
        self.db.execute('INSERT OR REPLACE INTO investigations VALUES(?,?,?,?,?,?)',
                        (scope, case['symptoms'], cause, encode(actions), who, redact(notes)))
        self.db.execute("UPDATE cases SET status='investigated' WHERE id=?", (case_id,))
        self.db.commit(); self.audit(f'incident:{case_id}',who,'investigate',notes)
        return self.capture(world, symptoms, cause, actions, obs)

    def verify(self, world, actions):
        ok, after = super().verify(world, actions)
        for action in actions:
            if action.startswith('recipe_'):
                passed, checks = world.recipe_verified(action[7:])
                after['checks'][action] = passed
                after.setdefault('recipe_checks', {})[action] = checks
                ok = ok and passed
        return ok, after


class InvestigatedAnalyser:
    def __init__(self, world, operator):
        self.world, self.operator = world, operator

    def analyse(self, symptoms, knowledge=None):
        _, scope = self.operator.context(self.world, symptoms, 'unknown', [], self.world.latest)
        row = self.operator.db.execute('SELECT * FROM investigations WHERE scope=? AND symptoms=?', (scope,encode(sorted(symptoms)))).fetchone()
        if row:
            return Diagnosis(row['cause'], 1.0, list(symptoms), 'investigation', json.loads(row['actions']))
        return Diagnosis('unknown', 0.0, list(symptoms))
