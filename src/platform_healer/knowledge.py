"""Durable scoped incidents and reviewed procedural learning, not model training."""
import sqlite3,time,json
from .model import digest,canonical
class Knowledge:
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=10,check_same_thread=False);self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS incidents(id INTEGER PRIMARY KEY,scope TEXT,cause TEXT,action TEXT,status TEXT,before TEXT,after TEXT,actor TEXT,reason TEXT,opened REAL,verified REAL);
        CREATE TABLE IF NOT EXISTS procedures(scope TEXT,cause TEXT,action TEXT,status TEXT,reviewer TEXT,PRIMARY KEY(scope,cause,action));
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at REAL,event TEXT,subject TEXT,actor TEXT,detail TEXT);
        """)
    def audit(self,event,subject,actor,detail):
        self.db.execute('INSERT INTO audit(at,event,subject,actor,detail) VALUES(?,?,?,?,?)',(time.time(),event,str(subject),actor,detail));self.db.commit()
    def resolve_unknown(self,target):
        rows=self.db.execute("SELECT id,before FROM incidents WHERE status='pending' AND action IS NULL AND cause='unknown'").fetchall()
        for row in rows:
            if json.loads(row['before']).get('target')==target:
                self.db.execute("UPDATE incidents SET status='resolved',reason='Fresh interpretable telemetry restored' WHERE id=?",(row['id'],))
                self.audit('telemetry_restored',row['id'],'monitor','Investigation resolved by fresh interpretable observation')
    def capture(self,sample,diagnosis):
        scope=digest({'identity':sample.identity,'kind':sample.kind,'target':sample.target,'protocol':1})
        row=self.db.execute("SELECT * FROM incidents WHERE scope=? AND cause=? AND action IS ? AND status IN ('pending','approved','executing') ORDER BY id DESC LIMIT 1",(scope,diagnosis.cause,diagnosis.action)).fetchone()
        if row:return dict(row)
        cur=self.db.execute('INSERT INTO incidents(scope,cause,action,status,before,opened) VALUES(?,?,?,?,?,?)',(scope,diagnosis.cause,diagnosis.action,'pending',canonical(sample.json()),time.time()));self.db.commit()
        return dict(self.db.execute('SELECT * FROM incidents WHERE id=?',(cur.lastrowid,)).fetchone())
    def approve(self,ident,actor,reason):
        if not actor.strip() or len(reason.strip())<8:raise ValueError('Named reviewer and meaningful reason required')
        cur=self.db.execute("UPDATE incidents SET status='approved',actor=?,reason=? WHERE id=? AND status='pending' AND action IS NOT NULL",(actor,reason,ident))
        if cur.rowcount!=1:self.db.rollback();raise ValueError('No pending bounded action')
        self.db.commit();self.audit('approve',ident,actor,reason)
    def authorised(self,case):
        auto=self.db.execute("SELECT 1 FROM procedures WHERE scope=? AND cause=? AND action=? AND status='validated'",(case['scope'],case['cause'],case['action'])).fetchone()
        return case['status']=='approved' or bool(auto)
    def outcome(self,ident,passed,after):
        case=self.db.execute('SELECT * FROM incidents WHERE id=?',(ident,)).fetchone()
        if not case or case['status'] not in ('approved','executing','pending'):raise ValueError('Invalid outcome transition')
        self.db.execute('UPDATE incidents SET status=?,after=?,verified=? WHERE id=?',('verified' if passed else 'failed',canonical(after),time.time() if passed else None,ident))
        self.db.execute('INSERT OR IGNORE INTO procedures VALUES(?,?,?,?,?)',(case['scope'],case['cause'],case['action'],'candidate',''))
        if not passed:self.db.execute("UPDATE procedures SET status='suspended' WHERE scope=? AND cause=? AND action=?",(case['scope'],case['cause'],case['action']))
        self.db.commit();self.audit('verified' if passed else 'failed',ident,'verifier','Independent outcome recorded')
    def promote(self,scope,cause,action,reviewer):
        if not reviewer.strip():raise ValueError('Reviewer required')
        failed=self.db.execute("SELECT COALESCE(MAX(id),0) FROM incidents WHERE scope=? AND cause=? AND action=? AND status='failed'",(scope,cause,action)).fetchone()[0]
        count=self.db.execute("SELECT count(*) FROM incidents WHERE scope=? AND cause=? AND action=? AND status='verified' AND id>?",(scope,cause,action,failed)).fetchone()[0]
        if count<2:raise ValueError('Two distinct verified occurrences after last failure are required')
        self.db.execute("INSERT INTO procedures VALUES(?,?,?,'validated',?) ON CONFLICT(scope,cause,action) DO UPDATE SET status='validated',reviewer=excluded.reviewer",(scope,cause,action,reviewer));self.db.commit();self.audit('promote',scope,reviewer,action)
    def suspend(self,scope,cause,action,reviewer):
        self.db.execute("UPDATE procedures SET status='suspended' WHERE scope=? AND cause=? AND action=?",(scope,cause,action));self.db.commit();self.audit('suspend',scope,reviewer,action)
    def export(self):return {name:[dict(r) for r in self.db.execute('SELECT * FROM '+name)] for name in ('incidents','procedures','audit')}
