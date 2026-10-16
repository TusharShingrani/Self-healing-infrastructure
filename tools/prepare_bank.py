"""Add the fictional statement schema and private lab PKI without deleting history."""
import json,shlex
from pathlib import Path
from expansion import transport,ROOT
from provision_expansion import put

def prepare():
    db=transport('db-1');db._ssh.timeout=180
    put(db,'/etc/healer-jobs/bank_schema.sql',(ROOT/'tools/job-host/bank_schema.sql').read_bytes(),True)
    code=r'''
import json,os,secrets,subprocess
from pathlib import Path
p=Path('/etc/healer-jobs/secrets.json');secret=json.loads(p.read_text())
for name in ('db_api_password','db_worker_password','second_api_token'):secret.setdefault(name,secrets.token_hex(32))
p.write_text(json.dumps(secret));p.chmod(0o600)
for role,key in [('bank_api','db_api_password'),('bank_worker','db_worker_password')]:
 sql="DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='"+role+"') THEN CREATE ROLE "+role+" LOGIN; END IF; END $$; ALTER ROLE "+role+" PASSWORD '"+secret[key]+"';"
 subprocess.run(['sudo','-u','postgres','psql','-v','ON_ERROR_STOP=1'],input=sql,text=True,check=True,stdout=subprocess.DEVNULL)
schema=Path('/etc/healer-jobs/bank_schema.sql').read_text()
subprocess.run(['sudo','-u','postgres','psql','-d','jobs_lab','-v','ON_ERROR_STOP=1'],input=schema,text=True,check=True,stdout=subprocess.DEVNULL)
base=Path('/etc/healer-bank/pki');base.mkdir(parents=True,mode=0o700,exist_ok=True)
def run(*args):subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
if not (base/'ca.key').exists():
 run('openssl','req','-x509','-newkey','rsa:3072','-nodes','-keyout',str(base/'ca.key'),'-out',str(base/'ca.crt'),'-days','365','-subj','/CN=Fictional Bank Lab CA','-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign')
for name,ip in [('database','10.1.1.83'),('api','10.1.1.80')]:
 if not (base/(name+'.crt')).exists():
  run('openssl','req','-new','-newkey','rsa:2048','-nodes','-keyout',str(base/(name+'.key')),'-out',str(base/(name+'.csr')),'-subj','/CN='+name)
  ext=base/(name+'.ext');ext.write_text('subjectAltName=IP:'+ip+'\nbasicConstraints=critical,CA:FALSE\nextendedKeyUsage=serverAuth\nkeyUsage=critical,digitalSignature,keyEncipherment\n')
  run('openssl','x509','-req','-in',str(base/(name+'.csr')),'-CA',str(base/'ca.crt'),'-CAkey',str(base/'ca.key'),'-CAcreateserial','-out',str(base/(name+'.crt')),'-days','90','-extfile',str(ext))
for f in base.glob('*.key'):f.chmod(0o600)
import pwd,grp
server=Path('/etc/healer-bank/server');server.mkdir(mode=0o750,exist_ok=True)
os.chown(server,0,grp.getgrnam('postgres').gr_gid)
for suffix in ('crt','key'):
 f=server/('database.'+suffix);f.write_bytes((base/('database.'+suffix)).read_bytes());f.chmod(0o640);os.chown(f,0,grp.getgrnam('postgres').gr_gid)
version=subprocess.check_output(['pg_lsclusters','--no-header'],text=True).split()[0]
conf=Path('/etc/postgresql')/version/'main'
(conf/'conf.d/bank-tls.conf').write_text("ssl=on\nssl_min_protocol_version='TLSv1.2'\nssl_cert_file='/etc/healer-bank/server/database.crt'\nssl_key_file='/etc/healer-bank/server/database.key'\n")
hba=conf/'pg_hba.conf';lines=[]
for role in ('bank_api','bank_worker'):
 for ip in ('10.1.1.81','10.1.1.82'):lines.append('hostssl jobs_lab '+role+' '+ip+'/32 scram-sha-256')
old=hba.read_text();hba.write_text('\n'.join(lines)+'\n'+ '\n'.join(l for l in old.splitlines() if not any(' '+r+' ' in l for r in ('bank_api','bank_worker')))+'\n')
subprocess.run(['systemctl','restart','postgresql@'+version+'-main'],check=True)
# Statement records are durable: the old hashing cleanup never touches them.
print('Statement schema, immutable records, restricted roles and verified-TLS certificates prepared')
'''
    ok,out,err=db._probe('sudo python3 -c '+shlex.quote(code))
    print(out,err[-1200:])
    if not ok:raise RuntimeError('Bank preparation failed; preserve pre-change backup')

if __name__=='__main__':prepare()
