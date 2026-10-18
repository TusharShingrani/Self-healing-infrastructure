"""Paired, bounded real-gateway comparison and refusal cases.

Run on the management host. Detailed histories and identities stay private.
Scripted approvals are laboratory operator actions, never healer self-approval.
"""
import argparse,http.cookiejar,json,random,secrets,ssl,sys,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'src'))
from deploy_lab import Admin
from platform_healer.transport import fixed_opener


def wait(check,seconds=70):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=check()
        if result:return result
        time.sleep(1)
    raise RuntimeError('Required gateway study condition did not become true')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--repetitions',type=int,default=3);args=parser.parse_args()
    if not 1<=args.repetitions<=5:raise ValueError('Study bounded to 1..5 comparisons per mode')
    admin=Admin(json.loads((ROOT/'config/educloud.json').read_text()))
    pki=Path.home()/'.config/platform-healer/pki'
    context=ssl.create_default_context(cafile=str(pki/'ca.crt'));context.load_cert_chain(str(pki/'monitor.crt'),str(pki/'monitor.key'))
    observer=fixed_opener(context)
    def independent(path):
        with observer.open('https://10.1.1.84:9106'+path,timeout=5) as response:return json.load(response)
    session=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def api(path,data=None):
        request=urllib.request.Request('http://127.0.0.1:8085'+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:8085'})
        with session.open(request,timeout=10) as response:return json.load(response)
    api('/login',{'token':(Path.home()/'.config/platform-healer/operator.token').read_text().strip()})
    def status():return api('/api/status')
    def sample():return status()['observations'].get('gateway-ports',{}).get('sample')
    def mode(value):api('/api/mode',{'target':'gateway-ports','mode':value,'actor':'study-operator','reason':'Explicit bounded gateway comparison: '+value})
    def idle():
        value=sample()
        return value and not value['error'] and value['metrics']['range']==[40000,40031] and value['metrics']['active_connections']==0 and value['metrics']['allocation_probe_errno']==0 and value['metrics']['client_transaction_ok'] and value
    destination=Path.home()/'.local/state/platform-healer/evidence'/('gateway-study-'+str(int(time.time()))+'.json')
    destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    evidence={'started':time.time(),'qualification':[],'trials':[],'refusals':[]}
    def save():destination.write_text(json.dumps(evidence,indent=2));destination.chmod(0o600)
    identity=wait(idle)['identity']
    host_range=admin.run('k8s-worker-2','cat /proc/sys/net/ipv4/ip_local_port_range').decode()
    last_action=0
    def trial(treatment,qualification=False):
        nonlocal last_action
        wait(idle)
        while time.time()<last_action+36:time.sleep(1)
        mode(treatment);before=status();ids={c['id'] for c in before['incidents']}
        name='study-'+str(int(time.time()))+'-'+secrets.token_hex(3)
        command='sudo systemd-run --collect --unit=platform-gateway-load-'+name+' --uid=ubuntu --property=RuntimeMaxSec=32 --property=MemoryMax=128M --property=TasksMax=100 --property=CPUQuota=25% --setenv=PYTHONPATH=/opt/platform-healer/src /usr/bin/python3 -m platform_healer.gateway_load --seconds 24 --concurrency 64 --name '+name
        started=time.time();admin.run('probe-1',command)
        case=None;approved=False
        while time.time()<started+27:
            snapshot=status()
            candidates=[c for c in snapshot['incidents'] if c['id'] not in ids and c['cause']=='gateway_outbound_port_exhaustion']
            if candidates:
                case=candidates[-1]
                if treatment=='reviewed' and case['status']=='pending' and time.time()-case['opened']>=2 and not approved:
                    api('/api/approve',{'incident':case['id'],'actor':'study-operator','reason':'Healthy upstream, repeated client/HAProxy failures and namespace EADDRNOTAVAIL; bounded port expansion reviewed'})
                    approved=True
            time.sleep(1)
        raw=admin.run('probe-1','cat /var/tmp/platform-gateway-results/'+name+'.json')
        load=json.loads(raw);end=load['started']+load['seconds']
        observations=[value for value in independent('/history') if load['started']<=value['time']<=end]
        failures=[value for value in observations if not value['success']]
        assert len(observations)>=8 and failures,'Fault did not produce enough actual independent HTTP failures'
        assert sample()['identity']==identity,'HAProxy identity changed during the trial'
        recovered=None
        for index in range(len(observations)-2):
            window=observations[index:index+3]
            if window[0]['time']>failures[0]['time'] and all(v['success'] for v in window):recovered=window[0]['time'];break
        if treatment=='observe':
            assert not recovered,'Observation-only unexpectedly recovered under held load'
            assert not any(e['incident'] in {c['id'] for c in status()['incidents'] if c['id'] not in ids} for e in status()['executions'])
        else:
            case=next(c for c in status()['incidents'] if c['id']==case['id'])
            assert case['status']=='verified' and case['verified']<=end+1 and recovered,'Repair was not verified while the background load was still active'
            if treatment=='automatic':assert case['actor'] is None,'Automatic comparison received a new approval'
            # Root cooldown is authoritative; the larger conservative wait also
            # avoids starting the next load during an earlier rollback lease.
            last_action=case['verified']
        result={'mode':treatment,'started':load['started'],'seconds':load['seconds'],'samples':len(observations),
            'failed_checks':len(failures),'successful_checks':len(observations)-len(failures),
            'first_failure_to_stable_recovery_seconds':None if recovered is None else recovered-failures[0]['time'],
            'case':case,'load':load,'observations':observations}
        evidence['qualification' if qualification else 'trials'].append(result);save()
        print(('QUALIFICATION' if qualification else 'TRIAL'),treatment,'failed checks',len(failures),'stable recovery',result['first_failure_to_stable_recovery_seconds'],flush=True)
        wait(idle)
        return case
    try:
        for _ in range(2):case=trial('reviewed',True)
        api('/api/promote',{'scope':case['scope'],'cause':case['cause'],'action':case['action'],'actor':'study-operator'})
        treatments=['observe','reviewed','automatic']*args.repetitions;random.Random(20261017).shuffle(treatments)
        evidence['order']=treatments
        for treatment in treatments:trial(treatment)
        mode('automatic');wait(idle)
        before_count=len(status()['executions'])
        admin.run('k8s-worker-2','sudo systemctl stop platform-gateway-upstream')
        wait(lambda:status()['observations']['gateway-ports']['cause']=='gateway_dependency_unavailable')
        time.sleep(4)
        assert len(status()['executions'])==before_count and sample()['metrics']['range']==[40000,40031]
        evidence['refusals'].append({'case':'upstream_unavailable','no_action':True,'observation':status()['observations']['gateway-ports']})
        admin.run('k8s-worker-2','sudo systemctl start platform-gateway-upstream');wait(idle)
        assert sample()['identity']==identity and host_range==admin.run('k8s-worker-2','cat /proc/sys/net/ipv4/ip_local_port_range').decode()
        evidence['passed']=True
    finally:
        admin.run('k8s-worker-2','sudo systemctl start platform-gateway-upstream')
        evidence['finished']=time.time();evidence['history']=status();save()
        print('Private study evidence:',destination,flush=True)
    print('PASS: real gateway comparison, learned reuse, wrong-repair refusal, unchanged patient and host range.',flush=True)


if __name__=='__main__':main()
