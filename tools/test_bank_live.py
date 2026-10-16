"""Controlled fictional-bank acceptance, security and scratch-restore checks.

Creates only synthetic statement requests and a uniquely named temporary copy
of jobs_lab for a restore test. Never restores over or drops the source DB.
Detailed output stays under ignored state/, not in public evidence.
"""
import argparse,base64,concurrent.futures,hashlib,json,shlex,socket,ssl,time,urllib.request,urllib.error,uuid
from pathlib import Path
from expansion import transport,ROOT

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--controlled-experiment',action='store_true');a=p.parse_args()
    if not a.controlled_experiment:p.error('Requires --controlled-experiment for the owned synthetic lab')
    out=ROOT/'state'/('bank-acceptance-'+str(time.time_ns())+'.json')
    config=json.loads((Path.home()/'.config/healer-jobs/client.json').read_text())
    ctx=ssl.create_default_context(cadata=base64.b64decode(config['ca']).decode())
    db=transport('db-1');ok,raw,_=db._probe('sudo cat /etc/healer-jobs/secrets.json')
    if not ok:raise RuntimeError('Private test client credential unavailable')
    second=json.loads(raw)['second_api_token']
    results={};ids=[]
    def request(path,data=None,token=None,context=ctx):
        req=urllib.request.Request(config['url']+path,data=None if data is None else json.dumps(data).encode(),headers={'Authorization':'Bearer '+(token or config['token']),'Content-Type':'application/json'})
        with urllib.request.urlopen(req,context=context,timeout=8) as response:return json.load(response)
    def refused(code,call):
        try:call()
        except urllib.error.HTTPError as e:return e.code==code
        return False
    key=str(uuid.uuid4());body={'period':'2026-09','idempotency_key':key}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:accepted=list(pool.map(lambda _:request('/statements',body),range(8)))
    ident=accepted[0]['id'];ids.append(ident)
    results['eight_concurrent_retries_one_request']=len({r['id'] for r in accepted})==1
    results['authentication_refused']=refused(401,lambda:request('/statements',token='invalid-test-token'))
    results['cross_account_read_refused']=refused(404,lambda:request('/statements/'+ident,token=second))
    results['caller_account_override_refused']=refused(400,lambda:request('/statements',dict(body,account_id='DEMO-NL-002')))
    results['legacy_hash_endpoint_removed']=refused(404,lambda:request('/jobs'))
    try:
        with urllib.request.urlopen(config['url']+'/readyz',timeout=5):pass
        results['untrusted_api_certificate_refused']=False
    except urllib.error.URLError as e:results['untrusted_api_certificate_refused']=isinstance(e.reason,ssl.SSLCertVerificationError)
    try:
        with socket.create_connection(('10.1.1.80',30080),timeout=5) as sock:
            with ctx.wrap_socket(sock,server_hostname='wrong-bank-name.invalid'):pass
        results['wrong_api_identity_refused']=False
    except ssl.SSLCertVerificationError:results['wrong_api_identity_refused']=True
    oracle=json.loads((ROOT/'tools/job-host/bank-oracle.json').read_text());deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        result=request('/statements/'+ident)
        if result['status']=='done':break
        time.sleep(.5)
    results['exact_entries_and_balances']=result.get('document')==oracle
    expected=hashlib.sha256(json.dumps(oracle,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    results['document_integrity_hash']=result.get('document_hash')==expected
    # Permission checks are rolled back, so even an unexpected grant cannot alter source data.
    code=r'''
import json,subprocess,uuid,psycopg2,hashlib
from pathlib import Path
ident=IDENT
checks={}
conn=psycopg2.connect(dbname='jobs_lab',user='postgres')
for role,query,label in [
 ('bank_api',"UPDATE bank_ledger SET amount_cents=amount_cents+1 WHERE entry_id='T001'",'api_cannot_change_ledger'),
 ('bank_worker',"DELETE FROM statement_requests",'worker_cannot_delete_requests'),
 ('bank_api',"UPDATE statement_requests SET status='done'",'api_cannot_complete_requests'),
 ('bank_worker',"UPDATE statement_requests SET document_hash=repeat('0',64) WHERE id='"+ident+"'",'completed_statement_immutable')]:
 try:
  with conn.cursor() as c:c.execute('SET LOCAL ROLE '+role);c.execute(query)
  checks[label]=False
 except psycopg2.Error:checks[label]=True
 finally:conn.rollback()
with conn.cursor() as c:
 c.execute("SELECT count(*) FROM bank_audit WHERE request_id=%s AND event='statement_accepted'",(ident,));checks['one_acceptance_audit_event']=c.fetchone()[0]==1
conn.close()
scratch='bank_restore_'+uuid.uuid4().hex
assert scratch.startswith('bank_restore_') and len(scratch)==45
dump=Path('/home/ubuntu')/(scratch+'.dump')
with dump.open('wb') as f:subprocess.run(['pg_dump','-Fc','jobs_lab'],stdout=f,check=True)
dump.chmod(0o600)
subprocess.run(['createdb',scratch],check=True)
try:
 with dump.open('rb') as f:subprocess.run(['pg_restore','--no-owner','--no-acl','--exit-on-error','-d',scratch],stdin=f,check=True,stdout=subprocess.DEVNULL)
 with psycopg2.connect(dbname=scratch,user='postgres') as restored:
  with restored.cursor() as c:
   c.execute('SELECT document,document_hash FROM statement_requests WHERE id=%s',(ident,));row=c.fetchone();checks['backup_restores_acknowledged_statement']=row is not None and row[0]==EXPECTED_DOCUMENT and row[1]==EXPECTED_HASH
   c.execute("SELECT count(*),sum(amount_cents) FROM bank_ledger WHERE account_id='DEMO-NL-001'");row=c.fetchone();checks['restored_ledger_reconciles']=row==(5,192206)
finally:
 if 'restored' in locals():restored.close()
 # Only the unique test copy is removed; the private dump is retained.
 assert scratch.startswith('bank_restore_') and scratch!='jobs_lab'
 subprocess.run(['dropdb',scratch],check=True)
# Also exercise the current schema against an empty disposable database.
fresh='bank_bootstrap_'+uuid.uuid4().hex
subprocess.run(['createdb',fresh],check=True)
try:
 subprocess.run(['psql','-d',fresh,'-v','ON_ERROR_STOP=1'],input=EXPECTED_SCHEMA,text=True,check=True,stdout=subprocess.DEVNULL)
 bootstrap=psycopg2.connect(dbname=fresh,user='postgres')
 try:
  with bootstrap.cursor() as c:
   c.execute("SELECT count(*),sum(amount_cents) FROM bank_ledger WHERE account_id='DEMO-NL-001'")
   checks['empty_database_schema_seed_reconciles']=c.fetchone()==(5,192206)
   c.execute("SELECT has_table_privilege('bank_api','bank_ledger','UPDATE'),has_table_privilege('bank_worker','statement_requests','DELETE')")
   checks['empty_database_roles_restricted']=c.fetchone()==(False,False)
 finally:bootstrap.close()
finally:
 assert fresh.startswith('bank_bootstrap_') and fresh!='jobs_lab'
 subprocess.run(['dropdb',fresh],check=True)
print(json.dumps(checks))
'''.replace('IDENT',repr(ident)).replace('EXPECTED_HASH',repr(expected)).replace('EXPECTED_DOCUMENT',repr(oracle)).replace('EXPECTED_SCHEMA',repr((ROOT/'tools/job-host/bank_schema.sql').read_text()))
    # Run as postgres, with its own home rather than any production credentials.
    code=code.replace("dump=Path('/home/ubuntu')", "dump=Path('/var/lib/postgresql')")
    db._ssh.timeout=180;ok,raw,err=db._probe('sudo -u postgres python3 -c '+shlex.quote(code))
    if not ok:
        out.write_text(json.dumps({'time':time.time(),'checks':results,'failure':err[-1200:]},indent=2)+'\n')
        raise RuntimeError('Bank database controls/restore test failed: '+err[-600:])
    results.update(json.loads(raw));out.write_text(json.dumps({'time':time.time(),'checks':results,'request_ids':ids},indent=2)+'\n')
    print(json.dumps({'checks':results,'passed':all(results.values()),'details':'retained privately in state/'},indent=2))
    if not all(results.values()):raise RuntimeError('Bank acceptance test did not pass')

if __name__=='__main__':main()
