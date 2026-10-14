"""Read-only final contract, model metadata, monitor and credential checks."""
import base64
import json
import os
import re
import shlex
import subprocess
import time
import urllib.request
from pathlib import Path
from infrastructure import build
from mapek.educloud import EduCloudWorld,load_lab


def main():
    world,operator,healer=build();observation=world.observe(False)
    if not world.health(observation):raise RuntimeError('Final infrastructure is not healthy')
    identity=world.repair_identity()
    procedures=operator.procedures()
    final={'time':time.time(),'healthy':True,'observation':observation,
           'validated_procedures':sum(p['status']=='validated' for p in procedures),
           'pending_cases':sum(c['status']=='pending' for c in operator.cases()),
           'procedure_references_match_deployed_contract':all(json.loads(p['scope'])['references']==identity['references'] for p in procedures if p['status']=='validated')}
    for address in ('10.1.1.60','10.1.1.61'):
        with urllib.request.urlopen('http://'+address+'/healthz',timeout=5) as r:
            final['nginx_'+address]=r.read().decode().strip()=='ok'
    with urllib.request.urlopen('http://10.1.1.50:9090/api/v1/targets',timeout=10) as r:
        data=json.loads(r.read())['data']['activeTargets']
        final['prometheus_targets']=[{'job':t['labels'].get('job'),'health':t['health'],'error':t.get('lastError','')} for t in data]
    lab=load_lab();monitor=EduCloudWorld(world.nodes['app-1'].cs,'monitor',lab,key_path=os.environ.get('LAB_SSH_KEY'))
    vm=monitor._refresh()
    if vm.get('projectid')!=lab['project_id'] or monitor.cs.ip_of(vm)!=lab['addresses']['monitor']:raise RuntimeError('Monitor ownership unproven')
    code="""import base64,json,urllib.request
from pathlib import Path
token=base64.b64encode(('admin:'+Path('/etc/grafana/admin-password').read_text().strip()).encode()).decode()
request=urllib.request.Request('http://127.0.0.1:3000/api/dashboards/uid/selfheal-infrastructure',headers={'Authorization':'Basic '+token})
with urllib.request.urlopen(request,timeout=10) as r:data=json.loads(r.read())['dashboard']
print(json.dumps({'uid':data['uid'],'title':data['title'],'panels':len(data['panels'])}))
"""
    ok,out,err=monitor._probe('sudo python3 -c '+shlex.quote(code))
    if not ok:raise RuntimeError('Grafana dashboard is not confirmed: '+err)
    final['grafana']=json.loads(out)
    final['advisor']=[dict(r) for r in healer.knowledge.db.execute('SELECT id,status,model,cause,actions FROM advice ORDER BY id')]
    Path('evidence/infrastructure-final-contract.json').write_text(json.dumps(final,indent=2)+'\n')
    # Check known real secrets without printing any of their values.
    secrets=[os.environ.get(n,'') for n in ('CS_KEY','CS_SECRET','GEMINI_API_KEY')]
    ok,out,_=world.command('app-2','sudo cat /etc/healer-stack/cache-admin-password')
    if ok:secrets.append(out.strip())
    ok,out,_=world.command('app-2','sudo cat /etc/healer-stack/cache-client.json')
    if ok:secrets.append(json.loads(out)['password'])
    changed=subprocess.check_output(['git','diff','--name-only'],text=True).splitlines()
    untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines()
    for name in set(changed+untracked):
        p=Path(name)
        if not p.is_file():continue
        raw=p.read_bytes()
        if any(s and s.encode() in raw for s in secrets) or re.search(rb'(?m)^-----BEGIN (OPENSSH|RSA|EC) PRIVATE KEY-----\r?$',raw):
            raise RuntimeError('Credential scan refused publication of '+name)
    print(json.dumps({'healthy':final['healthy'],'validated':final['validated_procedures'],'pending':final['pending_cases'],
                      'matching_contract':final['procedure_references_match_deployed_contract'],'targets':len(final['prometheus_targets']),
                      'all_targets_up':all(t['health']=='up' for t in final['prometheus_targets']), 'grafana':final['grafana'],
                      'advisor_models':[a['model'] for a in final['advisor']],'credential_scan':'PASS'},indent=2))


if __name__=='__main__':main()
