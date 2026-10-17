"""Management-host proof through the real Kubernetes controller's operator API.

Detailed output is private. This deliberately uses no direct Knowledge writes or
local Engine instance: approvals/promotion go through the deployed HTTP service.
"""
import http.cookiejar,json,os,sys,time,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from deploy_lab import Admin,ROOT


def wait(check,seconds=40):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=check()
        if result:return result
        time.sleep(1)
    raise RuntimeError('A required native-workflow condition did not become true')


def main():
    admin=Admin(json.loads((ROOT/'config/educloud.json').read_text()))
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def api(path,data=None):
        request=urllib.request.Request('http://10.1.1.80:30885'+path,
            data=None if data is None else json.dumps(data).encode(),
            headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:8085'})
        with opener.open(request,timeout=8) as response:return json.load(response)
    api('/login',{'token':(Path.home()/'.config/platform-healer/operator.token').read_text().strip()})
    def status():return api('/api/status')
    def sample(target):return status()['observations'].get(target,{}).get('sample')
    def demand(kind,count):
        if kind not in ('ports','descriptors') or count not in (0,96,128):raise ValueError('Unbounded fixture request')
        admin.run('k8s-worker-2',f"printf '%s' {count} | sudo tee /run/platform-healer/fixtures/{kind}/desired >/dev/null")
    root=Path.home()/'.local/state/platform-healer/evidence';root.mkdir(mode=0o700,parents=True,exist_ok=True)
    evidence={'started':time.time(),'runs':[],'channel':'deployed Kubernetes controller operator API'}
    # A repeat rehearsal must not silently auto-execute its first reviewed case.
    # Explicitly suspend previously learned permission; retain all old evidence.
    evidence['rehearsal_suspended_scopes']=[]
    for procedure in status()['procedures']:
        if procedure['status']=='validated' and procedure['cause'] in ('process_descriptor_exhaustion','outbound_port_exhaustion'):
            api('/api/suspend',{'scope':procedure['scope'],'cause':procedure['cause'],
                               'action':procedure['action'],'actor':'lab-rehearsal-operator'})
            evidence['rehearsal_suspended_scopes'].append(procedure['scope'])
    host_before=admin.run('k8s-worker-2','cat /proc/sys/net/ipv4/ip_local_port_range').decode()
    try:
        for occurrence in range(3):
            target='descriptors-canary'
            before=wait(lambda:sample(target))
            assert before['metrics']['soft_limit']==64
            old_ids={c['id'] for c in status()['incidents']}
            demand('descriptors',128)
            def incident():
                return next((c for c in status()['incidents'] if c['id'] not in old_ids and c['cause']=='process_descriptor_exhaustion'),None)
            case=wait(incident)
            if occurrence<2:
                assert case['status']=='pending'
                api('/api/approve',{'incident':case['id'],'actor':'lab-operator','reason':'Reviewed correlated EMFILE and approved per-process bounds'})
            def verified():
                return next((c for c in status()['incidents'] if c['id']==case['id'] and c['status']=='verified'),None)
            done=wait(verified)
            after=sample(target)
            assert after['identity']==before['identity'] and after['metrics']['held_fds']==128
            if occurrence==2:assert done['actor'] is None
            evidence['runs'].append(dict(kind='descriptors',occurrence=occurrence+1,
                decision='reviewed' if occurrence<2 else 'learned',before=before,after=after,
                incident=done,time=time.time()))
            demand('descriptors',0)
            wait(lambda:(sample(target) or {}).get('metrics',{}).get('soft_limit')==64)
            if occurrence==1:
                api('/api/promote',{'scope':done['scope'],'cause':done['cause'],'action':done['action'],'actor':'lab-operator'})
        target='ports-canary';before=wait(lambda:sample(target));old_ids={c['id'] for c in status()['incidents']}
        demand('ports',96)
        case=wait(lambda:next((c for c in status()['incidents'] if c['id'] not in old_ids and c['cause']=='outbound_port_exhaustion'),None))
        assert case['status']=='pending'
        api('/api/approve',{'incident':case['id'],'actor':'lab-operator','reason':'Reviewed isolated outbound allocation failure and reserved-port-safe range'})
        done=wait(lambda:next((c for c in status()['incidents'] if c['id']==case['id'] and c['status']=='verified'),None))
        after=sample(target)
        assert before['identity']==after['identity'] and after['metrics']['active_connections']>=96
        evidence['runs'].append(dict(kind='ports',before=before,after=after,incident=done,time=time.time()))
        demand('ports',0)
        wait(lambda:(sample(target) or {}).get('metrics',{}).get('range')==[40000,40031])
        assert host_before==admin.run('k8s-worker-2','cat /proc/sys/net/ipv4/ip_local_port_range').decode()
        evidence['passed']=True
    finally:
        for kind in ('ports','descriptors'):
            try:demand(kind,0)
            except Exception:pass
        evidence['finished']=time.time();evidence['history']=status()
        destination=root/('native-'+str(int(evidence['started']))+'.json')
        destination.write_text(json.dumps(evidence,indent=2));destination.chmod(0o600)
        print('Private native evidence:',destination,flush=True)
    print('PASS: native approval, two reviewed occurrences, promotion, autonomous reuse, network repair and rollback.',flush=True)

if __name__=='__main__':main()
