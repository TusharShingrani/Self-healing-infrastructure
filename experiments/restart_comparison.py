"""Three paired hard-restart / targeted-repair comparisons on the owned gateway.

Both actions follow the same confirmed diagnosis under continuing 24s/64 load.
This is administrator experiment code, never a new runtime restart capability.
Raw evidence remains private. Re-establishes pins only after load has drained.
"""
import argparse,http.cookiejar,json,secrets,ssl,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'src'))
from deploy_lab import Admin
from platform_healer.transport import fixed_opener


def recovery(observations,after):
    for index in range(len(observations)-2):
        window=observations[index:index+3]
        if window[0]['time']>=after and all(row['success'] for row in window):return window[0]['time']
    return None


def interruptions(events,begin,end):
    return sum(row['sent'] is not None and row['sent']<begin and begin<=row['finished']<end
               and row['result']=='connection_error' for row in events)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--confirm-owned-gateway-restart',action='store_true');args=parser.parse_args()
    if not args.confirm_owned_gateway_restart:raise ValueError('Explicit owned-gateway restart experiment flag required')
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
    def wait(check,seconds=85):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            result=check()
            if result:return result
            time.sleep(.5)
        raise RuntimeError('Comparison condition timed out; preserve partial evidence')
    def mode(value):api('/api/mode',{'target':'gateway-ports','mode':value,'actor':'restart-comparison-operator','reason':'Explicit paired restart versus bounded repair experiment'})
    def idle():
        s=sample()
        return s and not s['error'] and s['metrics']['range']==[40000,40031] and s['metrics']['active_connections']==0 and s['metrics']['allocation_probe_errno']==0 and s['metrics']['client_transaction_ok'] and s
    destination=Path.home()/'.local/state/platform-healer/evidence'/('restart-comparison-'+str(int(time.time()))+'.json')
    destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    evidence={'started':time.time(),'protocol':{'load_seconds':24,'concurrency':64,'trigger':'same correlated diagnosis; no deliberate approval delay','order':['restart','repair','repair','restart','restart','repair']},'trials':[],'requalification':[]}
    def save():
        temporary=destination.with_suffix('.tmp');temporary.write_text(json.dumps(evidence,indent=2));temporary.chmod(0o600);temporary.replace(destination)
    last_repair=0
    active_unit=None
    def repin():
        # Never turn an unknown identity into healthy during active load.
        time.sleep(3)
        admin.run('k8s-worker-2','sudo bash /opt/platform-healer/host/bootstrap-gateway.sh',timeout=30)
        wait(idle)
    def trial(treatment,qualification=False):
        nonlocal last_repair,active_unit
        mode('observe');initial=wait(idle)
        while time.time()<last_repair+36:time.sleep(.5)
        before=status();ids={row['id'] for row in before['incidents']};old_executions=len(before['executions'])
        pid_before=admin.run('k8s-worker-2','systemctl show platform-gateway.service -p MainPID --value').decode().strip()
        name='restart-study-'+str(int(time.time()))+'-'+secrets.token_hex(3);active_unit='platform-gateway-load-'+name
        command='sudo systemd-run --collect --unit='+active_unit+' --uid=ubuntu --property=RuntimeMaxSec=32 --property=MemoryMax=128M --property=TasksMax=100 --property=CPUQuota=25% --setenv=PYTHONPATH=/opt/platform-healer/src /usr/bin/python3 -m platform_healer.gateway_load --seconds 24 --concurrency 64 --record-events --name '+name
        started=time.time();admin.run('probe-1',command)
        def diagnosed():
            rows=[row for row in status()['incidents'] if row['id'] not in ids and row['cause']=='gateway_outbound_port_exhaustion' and row['status']=='pending']
            return rows[-1] if rows else None
        case=wait(diagnosed,12);begin=time.time()
        if treatment=='restart':
            action=admin.run('k8s-worker-2','sudo systemctl restart platform-gateway.service && systemctl show platform-gateway.service -p MainPID --value',timeout=10).decode().strip()
        else:
            mode('reviewed');api('/api/approve',{'incident':case['id'],'actor':'restart-comparison-operator','reason':'Same confirmed namespace exhaustion trigger as restart baseline; approved bounded capacity repair'})
            action='approved expand_port_range'
        end=time.time()
        while time.time()<started+28:time.sleep(.5)
        raw=json.loads(admin.run('probe-1','cat /var/tmp/platform-gateway-results/'+name+'.json'))
        active_unit=None
        assert raw['events_dropped']==0 and raw['threads_alive']==0,'Incomplete interruption timeline'
        stop=raw['started']+raw['seconds']
        checks=[row for row in independent('/history') if raw['started']<=row['time']<=stop]
        failures=[row for row in checks if not row['success']]
        assert len(checks)>=10 and failures and begin<stop-10,'Insufficient continuing load after action'
        stable=recovery(checks,begin)
        after=[row for row in checks if row['time']>=end]
        recurred=bool(stable is not None and any(not row['success'] for row in checks if row['time']>stable+2))
        result={'treatment':treatment,'started':raw['started'],'action_begin':begin,'action_end':end,'action':action,'baseline':initial,
            'independent_checks':checks,'failed_checks':len(failures),'checks':len(checks),
            'action_to_stable_recovery_seconds':None if stable is None else stable-begin,
            'first_failure_to_stable_recovery_seconds':None if stable is None else stable-failures[0]['time'],
            'failed_checks_after_action':sum(not row['success'] for row in after),'checks_after_action':len(after),
            'recurrence_after_stable_recovery':recurred,
            'any_success_then_failure_after_action':any(row['success'] and any(not later['success'] for later in after[index+1:]) for index,row in enumerate(after)),
            'pre_action_requests_transport_failed_before_planned_stop':interruptions(raw['events'],begin,stop),
            'pid_before':pid_before,
            'load':raw,'case':case}
        if treatment=='repair':
            current=status();case=next(row for row in current['incidents'] if row['id']==case['id'])
            assert case['status']=='verified' and case['verified']<stop and stable is not None,'Targeted repair did not verify under continuing load'
            assert sample()['identity']==initial['identity'],'Targeted repair restarted/replaced gateway'
            last_repair=case['verified'];result['case']=case
        else:
            assert len(status()['executions'])==old_executions,'Healer interfered with restart baseline'
            assert action!=pid_before and int(action)>1,'Restart did not replace gateway PID'
            assert admin.run('k8s-worker-2','sudo ip netns exec platform-healer-gateway sysctl -n net.ipv4.ip_local_port_range').decode().split()==['40000','40031']
            result['pid_after_restart']=action
        evidence['requalification' if qualification else 'trials'].append(result);save()
        print('QUALIFICATION' if qualification else 'PAIRED',treatment,'failed',len(failures),'recovery',result['action_to_stable_recovery_seconds'],'interrupted',result['pre_action_requests_transport_failed_before_planned_stop'],flush=True)
        if treatment=='restart':repin()
        else:wait(idle)
        return result
    try:
        mode('observe');wait(idle)
        host_range=admin.run('k8s-worker-2','cat /proc/sys/net/ipv4/ip_local_port_range')
        for treatment in evidence['protocol']['order']:trial(treatment)
        # A restart invalidates the old identity scope. Qualify the final one
        # explicitly; these extra checks are not part of the paired comparison.
        last=trial('repair',qualification=True)['case']
        api('/api/promote',{'scope':last['scope'],'cause':last['cause'],'action':last['action'],'actor':'restart-comparison-operator'})
        mode('automatic');wait(idle)
        assert host_range==admin.run('k8s-worker-2','cat /proc/sys/net/ipv4/ip_local_port_range')
        evidence['passed']=True
    except Exception as exc:
        evidence['error']=type(exc).__name__+': '+str(exc)[:200]
        raise
    finally:
        if active_unit:admin.run('probe-1','sudo systemctl stop '+active_unit+' || true')
        admin.run('k8s-worker-2','sudo systemctl start platform-gateway.service')
        if not evidence.get('passed'):
            mode('observe')
            try:
                wait(lambda:admin.run('k8s-worker-2','sudo ip netns exec platform-healer-gateway sysctl -n net.ipv4.ip_local_port_range').decode().split()==['40000','40031'],65)
                repin()
                evidence['failure_cleanup']='baseline and identity restored; observe-only pending operator review'
            except Exception:evidence['failure_cleanup']='operator inspection required; observe-only'
        evidence['finished']=time.time()
        try:evidence['history']=status()
        except Exception:evidence['history_error']='Controller snapshot unavailable'
        save()
        print('Private comparison evidence:',destination,flush=True)
    print('PASS: paired comparison complete; baseline healthy and automatic scope requalified.',flush=True)

if __name__=='__main__':main()
