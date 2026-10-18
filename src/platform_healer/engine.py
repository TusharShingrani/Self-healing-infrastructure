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
        self.streaks = {}
        self.observations = {}
        self.lock = threading.RLock()
        knowledge.db.execute("""CREATE TABLE IF NOT EXISTS executions(
            incident INTEGER PRIMARY KEY, target TEXT NOT NULL,
            envelope TEXT NOT NULL, status TEXT NOT NULL,
            deadline REAL NOT NULL, error TEXT NOT NULL DEFAULT '')""")
        knowledge.db.commit()
        knowledge.db.executescript("""CREATE TABLE IF NOT EXISTS target_modes(target TEXT PRIMARY KEY,mode TEXT,actor TEXT,reason TEXT,changed REAL);
            CREATE TABLE IF NOT EXISTS verification_windows(incident INTEGER PRIMARY KEY,successes INTEGER,started REAL,last_observation REAL DEFAULT 0);""")
        if 'last_observation' not in {r[1] for r in knowledge.db.execute('PRAGMA table_info(verification_windows)')}:
            knowledge.db.execute('ALTER TABLE verification_windows ADD COLUMN last_observation REAL DEFAULT 0');knowledge.db.commit()

    def mode(self,target):
        row=self.knowledge.db.execute('SELECT mode FROM target_modes WHERE target=?',(target,)).fetchone()
        return row['mode'] if row else self.targets[target].get('mode','automatic')

    def set_mode(self,target,mode,actor,reason):
        with self.lock:
            if target not in self.targets or mode not in ('observe','reviewed','automatic'):raise ValueError('Invalid target or mode')
            if not actor.strip() or len(reason.strip())<8:raise ValueError('Named operator and meaningful reason required')
            self.knowledge.db.execute('INSERT INTO target_modes VALUES(?,?,?,?,?) ON CONFLICT(target) DO UPDATE SET mode=excluded.mode,actor=excluded.actor,reason=excluded.reason,changed=excluded.changed',(target,mode,actor,reason,self.clock()))
            self.knowledge.db.commit();self.knowledge.audit('mode_change',target,actor,mode+': '+reason)

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
                                          'node':config.get('node','administrator-configured canary'),'mode':self.mode(target)}
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
                    signature=(sample.identity,diagnosis.cause,diagnosis.action)
                    old,count=self.streaks.get(target,(None,0))
                    self.streaks[target]=(signature,count+1 if old==signature else 1)
                    if diagnosis.action and self.streaks[target][1]<config.get('consecutive',1):
                        self.observations[target]['detail']+='; confirming sustained evidence before proposing a repair'
                        continue
                    if diagnosis.cause == 'healthy':
                        if sample.kind=='gateway_ports' and sample.metrics['gateway_transaction_ok'] and sample.metrics['client_transaction_ok'] and sample.metrics['active_connections']==0 and sample.metrics['allocation_probe_errno']==0:
                            self.knowledge.resolve_idle(target)
                        continue
                    case = self.knowledge.capture(sample, diagnosis)
                    mode=self.mode(target)
                    allowed=case['status']=='approved' or (mode=='automatic' and self.knowledge.authorised(case))
                    if diagnosis.action and mode!='observe' and allowed:
                        self._start(case, sample, config)
                except Exception as exc:
                    self.streaks.pop(target,None)
                    # Unreadable telemetry is visible; never turn it into healthy.
                    self.observations[target] = {'cause': 'unknown', 'detail': str(exc),
                                                 'time': self.clock()}
                    unknown=Sample(target,'unknown','unavailable:'+target,self.clock(),{},False,str(exc))
                    self.knowledge.capture(unknown,analyse(unknown,now=self.clock()))

    def _start(self, case, sample, config):
        db = self.knowledge.db
        if db.execute('SELECT 1 FROM executions WHERE incident=?', (case['id'],)).fetchone():
            return
        previous=db.execute('SELECT envelope FROM executions WHERE target=? ORDER BY incident DESC LIMIT 1',(sample.target,)).fetchone()
        if previous and config.get('cooldown_seconds',0):
            prior=json.loads(previous['envelope'])['payload']
            if self.clock()<prior['issued']+prior['lease']+config['cooldown_seconds']:
                self.observations[sample.target]['detail']+='; action deferred by cooldown'
                return
        expected = sample.metrics.get('range' if sample.kind in ('ports','gateway_ports') else 'soft_limit')
        if expected != config['baseline']:
            raise ValueError('Observed bound is not the reviewed baseline')
        envelope = intent(sample.target, sample.identity, case['action'], expected,
                          {'value': config['expanded']}, 'incident:' + str(case['id']),
                          config['key'], lease=config.get('lease',60), now=self.clock())
        # Commit the exact signed operation before any remote mutation. Restart
        # recovery asks for its status; it never invents another operation id.
        with db:
            db.execute('INSERT INTO executions(incident,target,envelope,status,deadline) VALUES(?,?,?,?,?)',
                       (case['id'], sample.target, json.dumps(envelope), 'dispatching', self.clock() + config.get('verification_timeout',20)))
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
                current=sample.metrics.get('range' if sample.kind in ('ports','gateway_ports') else 'soft_limit')
                if current!=envelope['payload']['parameters']['value']:
                    raise ValueError('Observed runtime bound does not match the approved repair')
                if sample.kind=='gateway_ports' and any(sample.metrics.get(name) is not True for name in ('upstream_healthy','gateway_transaction_ok','client_transaction_ok')):
                    raise RuntimeError('This verification observation does not show recovered gateway and independent client transactions')
                verification = config['client'].request('/verify/' + row['target'])
                if verification.get('verified') is not True:
                    raise RuntimeError('Independent resource operation has not recovered')
                if self.clock()>row['deadline']:raise RuntimeError('Verification deadline elapsed')
                window=db.execute('SELECT * FROM verification_windows WHERE incident=?',(row['incident'],)).fetchone()
                observation=sample.metrics.get('independent_probe_time',sample.time)
                if window and 'independent_probe_time' in sample.metrics and observation<=window['last_observation']:continue
                count=window['successes']+1 if window else 1;started=window['started'] if window else self.clock()
                db.execute('INSERT INTO verification_windows(incident,successes,started,last_observation) VALUES(?,?,?,?) ON CONFLICT(incident) DO UPDATE SET successes=excluded.successes,started=excluded.started,last_observation=excluded.last_observation',(row['incident'],count,started,observation));db.commit()
                if count<config.get('verification_samples',1) or self.clock()-started<config.get('verification_seconds',0):continue
                self.knowledge.outcome(row['incident'], True, dict(sample=sample.json(), verification=verification))
                db.execute("UPDATE executions SET status='verified',error='' WHERE incident=?", (row['incident'],))
                db.commit()
            except Exception as exc:
                db.execute('DELETE FROM verification_windows WHERE incident=?',(row['incident'],))
                if self.clock() >= row['deadline']:
                    self.knowledge.outcome(row['incident'], False, {'error': str(exc)})
                    db.execute("UPDATE executions SET status='failed',error=? WHERE incident=?", (str(exc), row['incident']))
                else:
                    db.execute('UPDATE executions SET error=? WHERE incident=?', (str(exc), row['incident']))
                db.commit()
