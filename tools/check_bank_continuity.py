"""Read-only post-experiment reconciliation. Detailed identifiers remain private."""
import hashlib,json,shlex
from expansion import transport,ROOT

def main():
    oracle=json.loads((ROOT/'tools/job-host/bank-oracle.json').read_text())
    expected=hashlib.sha256(json.dumps(oracle,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    code=r'''
import json,psycopg2
from contextlib import closing
with closing(psycopg2.connect(dbname='jobs_lab',user='postgres')) as db:
 db.set_session(readonly=True)
 with db.cursor() as c:
  c.execute("SELECT count(*) FROM bank_audit a LEFT JOIN statement_requests s ON s.id=a.request_id WHERE a.event='statement_accepted' AND s.id IS NULL")
  missing=c.fetchone()[0]
  c.execute("SELECT count(*) FROM statement_requests WHERE status<>'done'");pending=c.fetchone()[0]
  c.execute("SELECT document,document_hash FROM statement_requests WHERE account_id='DEMO-NL-001'");rows=c.fetchall()
  correct=bool(rows) and all(doc==ORACLE and hashed==EXPECTED for doc,hashed in rows)
  c.execute("SELECT count(*) FROM statement_requests s WHERE (SELECT count(*) FROM bank_audit a WHERE a.request_id=s.id AND a.event='statement_accepted')<>1 OR (s.status='done' AND (SELECT count(*) FROM bank_audit a WHERE a.request_id=s.id AND a.event='statement_completed')<>1)")
  bad_audit=c.fetchone()[0]
print(json.dumps({'accepted_records_missing':missing,'pending_requests':pending,'statements_checked':len(rows),'all_account_a_documents_exact':correct,'audit_count_mismatches':bad_audit,'passed':missing==0 and pending==0 and correct and bad_audit==0}))
'''.replace('ORACLE',repr(oracle)).replace('EXPECTED',repr(expected))
    db=transport('db-1');ok,out,err=db._probe('sudo -u postgres python3 -c '+shlex.quote(code))
    if not ok:raise RuntimeError('Read-only continuity check failed')
    result=json.loads(out);print(json.dumps(result,indent=2))
    if not result['passed']:raise RuntimeError('Continuity not established; investigate without modifying ledger')

if __name__=='__main__':main()
