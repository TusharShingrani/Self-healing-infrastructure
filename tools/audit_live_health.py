import json, subprocess, time, urllib.request
def fetch(url):
    with urllib.request.urlopen(url,timeout=8) as response:return response.read().decode()
data={"time":time.time(),"units":{},"health":{},"targets":[],"metrics":{},"resources":{}}
for unit in ('healer-loop','healer-infrastructure'):
    data['units'][unit]=subprocess.check_output(['systemctl','--user','show',unit,'-p','ActiveState','-p','SubState','-p','NRestarts','-p','WorkingDirectory'],text=True).strip().splitlines()
for ip in ('10.1.1.60','10.1.1.61'):data['health'][ip]=fetch('http://'+ip+'/healthz').strip()
state=json.loads(fetch('http://10.1.1.205:9106/status'))
data['health']['transaction']=state['observation']
data['infrastructure_tick_age_seconds']=round(time.time()-state['time'],1)
data['pending_incidents']=sum(c['status']=='pending' for c in state['cases'])
data['validated_procedures']=sum(p['status']=='validated' for p in state['procedures'])
targets=json.loads(fetch('http://10.1.1.50:9090/api/v1/targets'))['data']['activeTargets']
data['targets']=[{'job':t['labels']['job'],'health':t['health'],'error':t['lastError']} for t in targets]
for port in (9105,9106):
    data['metrics'][str(port)]=[line for line in fetch('http://10.1.1.205:'+str(port)+'/metrics').splitlines() if any(k in line for k in ('healthy','tick_errors','errors_total','last_tick','ticks_total'))]
data['resources']['memory']=subprocess.check_output(['free','-m'],text=True).strip()
data['resources']['disk']=subprocess.check_output(['df','-h','/'],text=True).strip()
data['recent_errors']=subprocess.run(['journalctl','--user','-u','healer-loop','-u','healer-infrastructure','--since','10 minutes ago','--no-pager'],capture_output=True,text=True).stdout
data['recent_errors']=[line[:500] for line in data['recent_errors'].splitlines() if any(s in line.lower() for s in ('tick error','traceback','host key','exception'))]
print(json.dumps(data,indent=2))
