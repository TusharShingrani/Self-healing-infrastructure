"""One bounded recording run. Reviewed mode NEVER submits an approval.

Run on the management host. Qualify procedures explicitly in the operator UI;
automatic mode refuses until the current exact scope is validated.
"""
import argparse,http.cookiejar,json,secrets,sys,time
from pathlib import Path
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from deploy_lab import Admin
from platform_healer.model import digest

def api_client():
    session=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def api(path,data=None):
        req=urllib.request.Request('http://127.0.0.1:8085'+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:8085'})
        with session.open(req,timeout=8) as response:return json.load(response)
    api('/login',{'token':(Path.home()/'.config/platform-healer/operator.token').read_text().strip()})
    return api

def idle(snapshot):
    sample=snapshot['observations'].get('gateway-ports',{}).get('sample',{})
    m=sample.get('metrics',{})
    return sample and -2<=time.time()-sample['time']<=5 and not sample.get('error') and m.get('range')==[40000,40031] and m.get('active_connections')==0 and m.get('allocation_probe_errno')==0 and m.get('reserved_conflict') is False and all(m.get(k) is True for k in ('client_transaction_ok','gateway_transaction_ok','upstream_healthy','headroom_safe'))

def require_automatic(snapshot,sample):
    scope=digest({'identity':sample['identity'],'kind':sample['kind'],'target':sample['target'],'protocol':1})
    if not any(p['scope']==scope and p['cause']=='gateway_outbound_port_exhaustion' and p['action']=='expand_port_range' and p['status']=='validated' for p in snapshot['procedures']):
        raise ValueError('Current procedure is not qualified. Review its verified outcomes in Knowledge and qualify it first.')

def run(api,admin,mode,actor,seconds=30):
    if mode not in ('reviewed','automatic') or not actor.strip() or not 5<=seconds<=30:raise ValueError('Invalid demo arguments')
    initial=api('/api/status')
    if not idle(initial):raise ValueError('Gateway is not at a fresh healthy idle baseline; do not inject load')
    sample=initial['observations']['gateway-ports']['sample'];identity=sample['identity']
    if mode=='automatic':require_automatic(initial,sample)
    old_mode=initial['policies']['gateway-ports']['mode'];ids={c['id'] for c in initial['incidents']}
    name='video-'+str(int(time.time()))+'-'+secrets.token_hex(3)
    destination=Path.home()/'.local/state/platform-healer/evidence'/(name+'.json');destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    events=[];case=None;verified_under_load=False
    command='sudo systemd-run --collect --unit=platform-gateway-load-'+name+' --uid=ubuntu --property=RuntimeMaxSec=38 --property=MemoryMax=128M --property=TasksMax=100 --property=CPUQuota=25% --setenv=PYTHONPATH=/opt/platform-healer/src /usr/bin/python3 -m platform_healer.gateway_load --seconds '+str(seconds)+' --concurrency 64 --name '+name
    api('/api/mode',{'target':'gateway-ports','mode':mode,'actor':actor,'reason':'Recording one bounded '+mode+' demonstration; no scripted approval or promotion'})
    try:
        print('BASELINE healthy; range 32; active connections 0',flush=True)
        print('MODE:',mode,flush=True)
        print('REMOTE COMMAND on probe-1:',command,flush=True)
        admin.run('probe-1',command);started=time.time()
        if mode=='reviewed':print('ACTION FOR OPERATOR: open the new incident and approve it in the UI. This runner will NOT approve it. Aim to approve within 15 seconds.',flush=True)
        else:print('Do not approve anything. The existing qualified procedure must supply permission.',flush=True)
        while time.time()<started+85:
            snapshot=api('/api/status');ob=snapshot['observations'].get('gateway-ports',{});sample=ob.get('sample',{});m=sample.get('metrics',{})
            cases=[c for c in snapshot['incidents'] if c['id'] not in ids and c['cause']=='gateway_outbound_port_exhaustion']
            if cases:case=cases[-1]
            event={'time':time.time(),'sample':sample,'incident':case};events.append(event)
            print(time.strftime('%H:%M:%S',time.gmtime()),'UTC', 'incident='+str(case['id'] if case else '-'),'status='+str(case['status'] if case else '-'),'ports='+str(m.get('used_ports'))+'/'+str(m.get('range_size')),'active='+str(m.get('active_connections')),'HTTP_OK='+str(m.get('client_transaction_ok')),'errno='+str(m.get('allocation_probe_errno')),flush=True)
            if sample.get('identity')!=identity:raise RuntimeError('Gateway identity changed; stop and investigate')
            if case and case['status']=='verified' and m.get('active_connections',0)>0 and m.get('client_transaction_ok') is True:
                verified_under_load=True
            if time.time()>started+seconds+2 and idle(snapshot):break
            time.sleep(1)
        if not case or case['status']!='verified' or not verified_under_load:raise RuntimeError('Recovery was not verified under continuing load. Preserve this failed demo; do not claim success. Approval may have been too late.')
        if mode=='automatic' and case.get('actor') is not None:raise RuntimeError('Automatic run received a fresh approval; invalid comparison')
        if not idle(api('/api/status')):raise RuntimeError('Baseline rollback was not confirmed')
        print('PASS: '+mode+' recovery verified under continuing load; same identity; baseline restored.',flush=True)
        return case
    finally:
        # The remote workload is independently bounded even if this CLI exits.
        # Mode restoration does not cancel the broker's safe lease rollback.
        try:api('/api/mode',{'target':'gateway-ports','mode':old_mode,'actor':actor,'reason':'Restore prior control mode after bounded video run'})
        finally:
            destination.write_text(json.dumps({'mode':mode,'events':events,'history':api('/api/status')},indent=2));destination.chmod(0o600)
            print('Private evidence:',destination,flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('reviewed','automatic'));parser.add_argument('--actor',required=True);args=parser.parse_args()
    run(api_client(),Admin(json.loads((ROOT/'config/educloud.json').read_text())),args.mode,args.actor)

if __name__=='__main__':main()
