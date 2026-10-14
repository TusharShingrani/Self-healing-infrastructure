"""Incident review and explicitly validated, narrowly scoped repair procedures.

Operator notes are evidence, never executable commands. Approval is single-use
and tied to the current VM identity and diagnosis. Validation needs two distinct
verified occurrences, then explicit human promotion. High-risk actions are never
eligible for automatic procedure execution.
"""
import json
import os
import sqlite3
import time
from .actions import CATALOGUE, HIGH_RISK
from .stages import Monitor


def encode(value):
    return json.dumps(value, sort_keys=True)


def redact(value):
    if isinstance(value, str):
        for name in ('CS_KEY', 'CS_SECRET', 'GEMINI_API_KEY'):
            secret = os.environ.get(name)
            if secret:
                value = value.replace(secret, '[REDACTED]')
        return value
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


class Operator:
    def __init__(self, path, clock=time.time):
        self.clock = clock
        self.db = sqlite3.connect(path, timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS cases (
          id INTEGER PRIMARY KEY, identity TEXT, scope TEXT, target TEXT,
          cause TEXT, symptoms TEXT, actions TEXT, evidence TEXT,
          status TEXT, opened REAL, expires REAL, operator TEXT, notes TEXT,
          after_evidence TEXT, verified INTEGER DEFAULT 0, procedure_id INTEGER);
        CREATE TABLE IF NOT EXISTS procedures (
          id INTEGER PRIMARY KEY, scope TEXT, cause TEXT, symptoms TEXT,
          actions TEXT, status TEXT, operator TEXT, created REAL,
          UNIQUE(scope,cause,symptoms,actions));
        CREATE TABLE IF NOT EXISTS operator_audit (
          id INTEGER PRIMARY KEY, time REAL, subject TEXT, operator TEXT, event TEXT, notes TEXT);
        ''')
        self.current = {}

    def context(self, world, symptoms, cause, actions, observation):
        lab = getattr(world, 'lab', {})
        vm = getattr(world, '_vm', None) or {}
        scope = {k: lab.get(k) for k in ('project_id', 'template_id', 'service',
                 'config_path', 'reference_dir', 'log_mount', 'log_image')}
        scope['target'] = getattr(world, 'name', 'simulated')
        repair_identity = world.repair_identity() if hasattr(world, 'repair_identity') else {'references': 'simulation', 'live_config': None}
        scope['references'] = repair_identity['references']
        stable = {k: observation.get(k) for k in
                  ('reachable', 'service_running', 'config_correct', 'http_ok')}
        stable['disk_critical'] = observation.get('disk_percent') is not None and observation['disk_percent'] >= 95
        stable['live_config'] = repair_identity['live_config']
        identity = encode([vm.get('id'), scope, sorted(symptoms), cause, actions, stable])
        return identity, encode(scope)

    def capture(self, world, symptoms, cause, actions, observation):
        lab = getattr(world, 'lab', {})
        if lab:
            vm = getattr(world, '_vm', None) or {}
            if (world.name not in lab.get('lab_instances', []) or not lab.get('project_id')
                    or vm.get('projectid') != lab['project_id']):
                raise ValueError('Managed target ownership is not positively proven')
        if any(a not in CATALOGUE for a in actions):
            raise ValueError('Unknown action; operator notes cannot introduce commands')
        identity, scope = self.context(world, symptoms, cause, actions, observation)
        row = self.db.execute("SELECT * FROM cases WHERE identity=? AND status IN ('pending','approved','running','rejected') ORDER BY id DESC LIMIT 1", (identity,)).fetchone()
        if row:
            if row['status'] == 'approved' and (row['expires'] or 0) <= self.clock():
                self.db.execute("UPDATE cases SET status='pending',expires=NULL WHERE id=?", (row['id'],))
                self.db.commit()
                return self.case(row['id'])
            return dict(row)
        evidence = world.diagnostic_evidence() if hasattr(world, 'diagnostic_evidence') else {'observation': observation}
        evidence['observation'] = observation
        evidence['hypothesis'] = cause
        evidence['certainty'] = 'hypothesis requiring operator review'
        evidence['plan'] = {
            'actions': actions,
            'risk': 'high' if any(a in HIGH_RISK for a in actions) else 'guest repair',
            'expected_outcome': 'required service probes pass and action-specific cause checks pass',
            'verification': ['fresh direct service/config/HTTP probes'] +
                (['bounded log space below 80%'] if 'clear_logs' in actions else []) +
                (['rotation matches reference and flood timer inactive'] if 'fix_log_rotation' in actions else []),
            'scope': json.loads(scope),
        }
        cur = self.db.execute('INSERT INTO cases(identity,scope,target,cause,symptoms,actions,evidence,status,opened) VALUES(?,?,?,?,?,?,?,?,?)',
            (identity, scope, getattr(world, 'name', 'simulated'), cause,
             encode(sorted(symptoms)), encode(actions), encode(redact(evidence)), 'pending', self.clock()))
        self.db.commit()
        return self.case(cur.lastrowid)

    def authorize(self, world, symptoms, cause, actions, observation):
        observation = world.observe(sample=False)
        case = self.capture(world, symptoms, cause, actions, observation)
        self.current[case['target']] = case['id']
        proc = self.db.execute("SELECT id FROM procedures WHERE scope=? AND cause=? AND symptoms=? AND actions=? AND status='validated'", (case['scope'], cause, case['symptoms'], case['actions'])).fetchone()
        automatic = (bool(proc) and set(symptoms) <= set(Monitor().symptoms(observation))
                     and cause != 'unknown' and not any(a in HIGH_RISK for a in actions))
        approved = case['status'] == 'approved' and (case['expires'] or 0) > self.clock()
        if not automatic and not approved:
            return False, f"incident #{case['id']} requires review: tools/incidents.py show {case['id']}"
        if 'clear_logs' in actions and hasattr(world, 'assert_bounded_log_mount'):
            world.assert_bounded_log_mount()
        cur = self.db.execute("UPDATE cases SET status='running',procedure_id=? WHERE id=? AND status IN ('pending','approved')", (proc['id'] if automatic else None, case['id']))
        self.db.commit()
        return cur.rowcount == 1, f"incident #{case['id']}"

    def decide(self, case_id, approve, who, notes):
        if not who.strip() or not notes.strip():
            raise ValueError('Operator identity and rationale are required')
        cur = self.db.execute("UPDATE cases SET status=?,operator=?,notes=?,expires=? WHERE id=? AND status='pending'", ('approved' if approve else 'rejected', who, redact(notes), self.clock()+900, case_id))
        self.db.commit()
        if cur.rowcount:
            self.audit(f'incident:{case_id}', who, 'approve' if approve else 'reject', notes)
        return cur.rowcount == 1

    def audit(self, subject, who, event, notes):
        self.db.execute('INSERT INTO operator_audit(time,subject,operator,event,notes) VALUES(?,?,?,?,?)', (self.clock(), subject, who, event, redact(notes)))
        self.db.commit()

    def verify(self, world, actions):
        obs = world.observe(sample=False)
        checks = {'required_probes': world.health(obs)}
        if 'restore_config' in actions:
            checks['valid_configuration'] = world.configuration_verified() if hasattr(world, 'configuration_verified') else obs.get('config_correct') is True
        if 'clear_logs' in actions:
            checks['space_reclaimed'] = obs.get('disk_percent') is not None and obs['disk_percent'] < 80
            if hasattr(world, 'assert_bounded_log_mount'):
                try:
                    world.assert_bounded_log_mount(); checks['bounded_log_mount'] = True
                except RuntimeError:
                    checks['bounded_log_mount'] = False
        if 'fix_log_rotation' in actions:
            checks['rotation_restored'] = world.rotation_verified() if hasattr(world, 'rotation_verified') else False
        return all(checks.values()), {'observation': obs, 'checks': checks}

    def finish(self, world, execution_ok):
        case_id = self.current.pop(getattr(world, 'name', 'simulated'), None)
        if case_id is None:
            return False
        case = self.case(case_id)
        verified, after = self.verify(world, json.loads(case['actions']))
        if 'rebuild_instance' not in json.loads(case['actions']):
            verified = verified and (getattr(world, '_vm', None) or {}).get('id') == json.loads(case['identity'])[0]
        ok = bool(execution_ok and verified)
        self._close(case, ok, after)
        return ok

    def record_human(self, world, case_id, actions, who, notes):
        case = self.case(case_id)
        if case['status'] not in ('pending', 'approved', 'cleared') or case['target'] != world.name:
            raise ValueError('Incident is closed or belongs to another target')
        if not actions or any(a not in CATALOGUE or a in HIGH_RISK for a in actions):
            raise ValueError('Human repairs must map to supported guest actions')
        if not who.strip() or not notes.strip():
            raise ValueError('Describe the actual changes and operator identity')
        # Positive identity proof; do not certify a replacement against an old case.
        current_id = (getattr(world, '_vm', None) or {}).get('id')
        if current_id != json.loads(case['identity'])[0]:
            raise ValueError('VM identity changed; open a new incident')
        self.db.execute('UPDATE cases SET actions=?,operator=?,notes=? WHERE id=?', (encode(actions), who, redact(notes), case_id))
        self.db.commit()
        case = self.case(case_id)
        ok, after = self.verify(world, actions)
        ok = ok and (getattr(world, '_vm', None) or {}).get('id') == json.loads(case['identity'])[0]
        _, current_scope = self.context(world, json.loads(case['symptoms']), case['cause'], actions, after['observation'])
        ok = ok and current_scope == case['scope']
        self.audit(f'incident:{case_id}', who, 'record-human', notes)
        self._close(case, ok, after)
        return ok

    def reconcile(self, world, observation):
        # Clearing an observed condition is not proof of a repair procedure.
        if world.health(observation) and not Monitor().symptoms(observation):
            self.db.execute("UPDATE cases SET status='cleared' WHERE target=? AND status IN ('pending','approved','rejected')", (getattr(world, 'name', 'simulated'),))
            self.db.commit()

    def _close(self, case, ok, after):
        self.db.execute('UPDATE cases SET status=?,verified=?,after_evidence=? WHERE id=?', ('verified' if ok else 'failed', int(ok), encode(redact(after)), case['id']))
        if not ok and case['procedure_id']:
            self.db.execute("UPDATE procedures SET status='revoked' WHERE id=?", (case['procedure_id'],))
        if ok and json.loads(case['actions']) and not any(a in HIGH_RISK for a in json.loads(case['actions'])):
            self.db.execute("INSERT OR IGNORE INTO procedures(scope,cause,symptoms,actions,status,created) VALUES(?,?,?,?,'candidate',?)", (case['scope'], case['cause'], case['symptoms'], case['actions'], self.clock()))
        self.db.commit()

    def promote(self, procedure_id, who):
        proc = self.db.execute('SELECT * FROM procedures WHERE id=?', (procedure_id,)).fetchone()
        if not proc or not who.strip():
            raise ValueError('Procedure and reviewer required')
        count = self.db.execute('SELECT COUNT(*) FROM cases WHERE scope=? AND cause=? AND symptoms=? AND actions=? AND verified=1', (proc['scope'], proc['cause'], proc['symptoms'], proc['actions'])).fetchone()[0]
        if count < 2 or not json.loads(proc['scope']).get('references') or proc['cause'] == 'unknown' or any(a in HIGH_RISK for a in json.loads(proc['actions'])):
            raise ValueError('Two distinct verified occurrences are required; high-risk procedures cannot be automatic')
        self.db.execute("UPDATE procedures SET status='validated',operator=? WHERE id=?", (who, procedure_id))
        self.db.commit()
        self.audit(f'procedure:{procedure_id}', who, 'promote', 'Two distinct verified occurrences reviewed')

    def case(self, case_id):
        row = self.db.execute('SELECT * FROM cases WHERE id=?', (case_id,)).fetchone()
        if not row:
            raise ValueError('Incident not found')
        return dict(row)

    def cases(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM cases ORDER BY id DESC')]

    def procedures(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM procedures ORDER BY id')]
