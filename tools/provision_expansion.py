"""Provision only recorded expansion nodes; private configuration never enters Git."""
import argparse,base64,json,os,shlex
from pathlib import Path
from expansion import transport,CONFIG,ROOT

def put(world,path,data,private=False):
    encoded=base64.b64encode(data).decode()
    code=f"from pathlib import Path;import base64,os;p=Path({path!r});p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode({encoded!r}));os.chmod(p,{0o600 if private else 0o644})"
    ok,out,err=world._probe('sudo python3 -c '+shlex.quote(code))
    if not ok:raise RuntimeError('File transfer failed; refusing installer execution')

def run(name):
    world=transport(name)
    for relative in ('tools/install_expansion_host.sh','tools/job-host/db_metrics.py','tools/job-host/probe.py','tools/job-host/app.py','tools/job-host/banking.py','tools/job-host/bank-oracle.json','tools/job-host/policy_witness.py','tools/job-host/Dockerfile'):
        put(world,'/home/ubuntu/job-lab/'+relative,(ROOT/relative).read_bytes())
    role=CONFIG['nodes'][name]['role']
    if role=='worker':
        control=transport('k8s-control');ok,token,err=control._probe('sudo cat /var/lib/rancher/k3s/server/node-token')
        if not ok:raise RuntimeError('Private cluster join token unavailable')
        # JSON is valid YAML, and avoids interpolating a secret into a shell command.
        cfg={'server':'https://10.1.1.80:6443','token':token.strip(),'node-name':name,'node-ip':CONFIG['nodes'][name]['address']}
        put(world,'/etc/rancher/k3s/config.yaml',json.dumps(cfg).encode(),True)
        role='worker-1' if name.endswith('-1') else 'worker-2'
    if role=='observer':
        db=transport('db-1');ok,raw,_=db._probe('sudo cat /etc/healer-jobs/secrets.json')
        if not ok:raise RuntimeError('Restricted client token unavailable')
        ok,bank_ca,_=db._probe('sudo cat /etc/healer-bank/pki/ca.crt')
        if not ok:raise RuntimeError('Prepare bank TLS before provisioning the observer')
        cfg={'url':CONFIG['api_url'],'token':json.loads(raw)['api_token'],'ca':base64.b64encode(bank_ca.encode()).decode()}
        put(world,'/etc/healer-jobs/client.json',json.dumps(cfg).encode(),True)
    world._ssh.timeout=1200  # Provisioning is separate from short repair/probe timeouts.
    ok,out,err=world._probe('sudo bash /home/ubuntu/job-lab/tools/install_expansion_host.sh '+shlex.quote(role)+' '+shlex.quote(CONFIG['k3s_version']))
    print(name,out[-2000:],err[-1000:],flush=True)
    if not ok:raise RuntimeError('Host installer failed: '+name)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('name',choices=list(CONFIG['nodes']));args=parser.parse_args();run(args.name)
