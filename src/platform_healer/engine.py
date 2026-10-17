"""Serial MAPE-K controller with durable operation identity and bounded verification.

No API caller supplies an executable command or an action parameter. Root policy
and controller configuration must agree on the two reviewed resource bounds.
"""
import json
import threading
import time

from .analyse import analyse
from .model import Sample, intent


class Engine:
    def __init__(self, knowledge, targets, clock=time.time):
        self.knowledge = knowledge
        self.targets = targets
        self.clock = clock
        self.previous = {}
        self.observations = {}
        self.lock = threading.RLock()
        knowledge.db.execute("""CREATE TABLE IF NOT EXISTS executions(
            incident INTEGER PRIMARY KEY, target TEXT NOT NULL,
            envelope TEXT NOT NULL, status TEXT NOT NULL,
            deadline REAL NOT NULL, error TEXT NOT NULL DEFAULT '')""")
        knowledge.db.commit()

    def approve(self, incident, actor, reason):
        with self.lock:
            self.knowledge.approve(incident, actor, reason)

    def promote(self, scope, cause, action, actor):
        with self.lock:
            self.knowledge.promote(scope, cause, action, actor)

    def snapshot(self):
        with self.lock:
            return dict(self.knowledge.export(), observations=dict(self.observations),
                        policies={target:{'baseline':config['baseline'],'expanded':config['expanded'],
                                          'node':config.get('node','administrator-configured canary')}
                                  for target,config in self.targets.items()},
                        executions=[dict(r) for r in self.knowledge.db.execute(
                            'SELECT incident,target,status,deadline,error FROM executions')])

    def tick(self):
        with self.lock:
            self._resume()
            for target, config in self.targets.items():
                try:
                    sample = Sample(**config['client'].request('/sample/' + target))
                    if sample.target != target:
                        raise ValueError('Agent returned a different target')
                    diagnosis = analyse(sample, self.previous.get(target), self.clock())
                    if diagnosis.cause!='unknown':self.knowledge.resolve_unknown(target)
                    self.observations[target] = dict(sample=sample.json(),
                        cause=diagnosis.cause, detail=diagnosis.detail)
                    self.previous[target] = sample
                    if diagnosis.cause == 'healthy':
                        continue
                    case = self.knowledge.capture(sample, diagnosis)
                    if diagnosis.action and self.knowledge.authorised(case):
                        self._start(case, sample, config)
                except Exception as exc:
                    # Unreadable telemetry is visible; never turn it into healthy.
                    self.observations[target] = {'cause': 'unknown', 'detail': str(exc),
                                                 'time': self.clock()}
                    unknown=Sample(target,'unknown','unavailable:'+target,self.clock(),{},False,str(exc))
                    self.knowledge.capture(unknown,analyse(unknown,now=self.clock()))

    def _start(self, case, sample, config):
        db = self.knowledge.db
        if db.execute('SELECT 1 FROM executions WHERE incident=?', (case['id'],)).fetchone():
            return
        expected = sample.metrics.get('range' if sample.kind == 'ports' else 'soft_limit')
        if expected != config['baseline']:
            raise ValueError('Observed bound is not the reviewed baseline')
        envelope = intent(sample.target, sample.identity, case['action'], expected,
                          {'value': config['expanded']}, 'incident:' + str(case['id']),
                          config['key'], lease=config.get('lease',60), now=self.clock())
        # Commit the exact signed operation before any remote mutation. Restart
        # recovery asks for its status; it never invents another operation id.
        with db:
            db.execute('INSERT INTO executions(incident,target,envelope,status,deadline) VALUES(?,?,?,?,?)',
                       (case['id'], sample.target, json.dumps(envelope), 'dispatching', self.clock() + 20))
            db.execute("UPDATE incidents SET status='executing' WHERE id=?", (case['id'],))
        try:
            result = config['client'].request('/execute', envelope)
            if result.get('status') != 'applied':
                raise RuntimeError('Broker has not confirmed application')
            db.execute("UPDATE executions SET status='verifying' WHERE incident=?", (case['id'],))
            db.commit()
        except Exception as exc:
            # A timeout is ambiguous: recovery reconciles the durable broker
            # journal instead of repeating a potentially successful syscall.
            db.execute('UPDATE executions SET error=? WHERE incident=?', (str(exc), case['id']))
            db.commit()

    def _resume(self):
        db = self.knowledge.db
        for row in db.execute("SELECT * FROM executions WHERE status IN ('dispatching','verifying')").fetchall():
            config = self.targets.get(row['target'])
            try:
                if config is None:
                    raise ValueError('Target configuration removed')
                envelope = json.loads(row['envelope'])
                operation = config['client'].request('/operation/' + envelope['payload']['id'])
                if operation.get('status') != 'applied':
                    raise RuntimeError('No active applied lease')
                sample = Sample(**config['client'].request('/sample/' + row['target']))
                if not sample.valid(self.clock()) or sample.identity != envelope['payload']['identity']:
                    raise ValueError('Verification target changed or telemetry stale')
                current=sample.metrics.get('range' if sample.kind=='ports' else 'soft_limit')
                if current!=envelope['payload']['parameters']['value']:
                    raise ValueError('Observed runtime bound does not match the approved repair')
                verification = config['client'].request('/verify/' + row['target'])
                if verification.get('verified') is not True:
                    raise RuntimeError('Independent resource operation has not recovered')
                self.knowledge.outcome(row['incident'], True, dict(sample=sample.json(), verification=verification))
                db.execute("UPDATE executions SET status='verified',error='' WHERE incident=?", (row['incident'],))
                db.commit()
            except Exception as exc:
                if self.clock() >= row['deadline']:
                    self.knowledge.outcome(row['incident'], False, {'error': str(exc)})
                    db.execute("UPDATE executions SET status='failed',error=? WHERE incident=?", (str(exc), row['incident']))
                else:
                    db.execute('UPDATE executions SET error=? WHERE incident=?', (str(exc), row['incident']))
                db.commit()
