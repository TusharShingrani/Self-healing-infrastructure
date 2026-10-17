"""Root-side intent journal and compare-and-set rollback leases."""
import json,sqlite3,threading,time
from .model import authenticate,canonical,digest
class Broker:
    def __init__(self,path,key,plugins,clock=time.time):
        if len(key)<32:raise ValueError('A private key of at least 32 bytes is required')
        self.key,self.plugins,self.clock=key,plugins,clock;self.lock=threading.RLock()
        self.db=sqlite3.connect(path,check_same_thread=False,timeout=10);self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute("CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,target TEXT,identity TEXT,action TEXT,intent_hash TEXT,before TEXT,after TEXT,expires REAL,status TEXT,detail TEXT)");self.db.commit()
        self.db.execute('CREATE TABLE IF NOT EXISTS refusals(id TEXT PRIMARY KEY,target TEXT,action TEXT,reason TEXT,at REAL)');self.db.commit()
    def execute(self,envelope):
        with self.lock:
            p=authenticate(envelope,self.key,self.clock())
            if self.db.execute('SELECT 1 FROM refusals WHERE id=?',(p['id'],)).fetchone():raise ValueError('This operation was refused; a fresh reviewed intent is required')
            row=self.db.execute('SELECT * FROM operations WHERE id=?',(p['id'],)).fetchone()
            if row:
                if row['intent_hash']!=digest(p):raise ValueError('Operation id reused with changed intent')
                return dict(row)
            if p['target'] not in self.plugins:raise ValueError('Target outside root-owned policy')
            plugin=self.plugins[p['target']];snapshot=plugin.sample()
            if not snapshot.valid(self.clock()) or snapshot.identity!=p['identity']:raise ValueError('Target identity or telemetry changed')
            if p['action']!=plugin.action:raise ValueError('Action not permitted for this target')
            if plugin.value()!=p['expected']:raise ValueError('Compare-and-set precondition failed')
            if set(p['parameters'])!={'value'}:raise ValueError('Unsupported action parameters')
            try:value=plugin.validate(p['parameters']['value'])
            except ValueError as exc:
                self._refuse(p,str(exc));raise
            if any(x['target']==p['target'] for x in self.active()):raise ValueError('Target already has an active lease')
            cooldown=getattr(plugin,'cooldown_seconds',0)
            if cooldown:
                latest=self.db.execute('SELECT expires FROM operations WHERE target=? ORDER BY expires DESC LIMIT 1',(p['target'],)).fetchone()
                if latest and self.clock()<latest['expires']+cooldown:
                    self._refuse(p,'Target cooldown has not elapsed');raise ValueError('Target cooldown has not elapsed')
            before=plugin.value()
            self.db.execute('INSERT INTO operations VALUES(?,?,?,?,?,?,?,?,?,?)',(p['id'],p['target'],p['identity'],p['action'],digest(p),canonical(before),canonical(value),self.clock()+p['lease'],'applying','Intent persisted before mutation'));self.db.commit()
            try:
                plugin.apply(value)
                if plugin.value()!=value:raise RuntimeError('Mutation readback differs')
                self._status(p['id'],'applied','Runtime value verified; useful-work verification still required')
            except Exception as exc:
                self._status(p['id'],'rollback_pending',type(exc).__name__+': '+str(exc)[:200]);self.reconcile(force_ids={p['id']})
                raise RuntimeError('Mutation failed; inspect journal and rollback status') from exc
            return self.operation(p['id'])
    def operation(self,ident):
        with self.lock:
            row=self.db.execute('SELECT * FROM operations WHERE id=?',(ident,)).fetchone()
            if not row:raise ValueError('Unknown operation')
            return dict(row)
    def _refuse(self,p,reason):
        self.db.execute('INSERT OR IGNORE INTO refusals VALUES(?,?,?,?,?)',(p['id'],p['target'],p['action'],reason[:240],self.clock()));self.db.commit()
    def active(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM operations WHERE status IN ('applying','applied','rollback_pending','rollback_deferred')")]
    def _status(self,ident,status,detail):
        self.db.execute('UPDATE operations SET status=?,detail=? WHERE id=?',(status,detail,ident));self.db.commit()
    def reconcile(self,force_ids=frozenset(),recover=False):
        with self.lock:
            for row in self.active():
                if not recover and row['id'] not in force_ids and row['status'] not in ('applying','rollback_pending','rollback_deferred') and row['expires']>self.clock():continue
                plugin=self.plugins.get(row['target'])
                if not plugin:self._status(row['id'],'conflict','Target removed from policy; operator must inspect');continue
                try:
                    current=plugin.sample()
                    if current.identity!=row['identity']:self._status(row['id'],'identity_changed','No mutation of replacement target');continue
                    value=plugin.value();before=json.loads(row['before']);after=json.loads(row['after'])
                    if value==before:self._status(row['id'],'rolled_back','Baseline already restored');continue
                    if value!=after:self._status(row['id'],'conflict','Administrator or another owner changed the value');continue
                    if not plugin.rollback_ready(before):self._status(row['id'],'rollback_deferred','Current use exceeds safe baseline; operator visible deferred rollback');continue
                    plugin.apply(before)
                    if plugin.value()!=before:raise RuntimeError('Rollback readback failed')
                    self._status(row['id'],'rolled_back','Compare-and-set baseline restoration verified')
                except Exception as exc:self._status(row['id'],'rollback_deferred',type(exc).__name__+': '+str(exc)[:160])
