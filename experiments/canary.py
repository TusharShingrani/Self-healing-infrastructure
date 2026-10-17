"""Run on the owned canary as root. Private detailed evidence stays off Git.

Three genuinely distinct descriptor-pressure occurrences: two operator-approved
repairs, explicit procedure promotion, then one learned automatic repair.
"""
import json, os, time
from pathlib import Path
from platform_healer.engine import Engine
from platform_healer.knowledge import Knowledge
from platform_healer.transport import UnixClient


def wait(check, seconds=25):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        value=check()
        if value:return value
        time.sleep(.5)
    raise RuntimeError('Timed out awaiting a required experiment condition')


def main():
    if os.geteuid()!=0:raise RuntimeError('Owned fixture controls require administrator')
    root=Path('/var/lib/platform-healer/experiment-'+str(int(time.time())))
    root.mkdir(mode=0o700)
    client=UnixClient('/run/platform-healer/broker.sock')
    def ready():
        try:
            return all(client.request('/sample/'+target).get('identity')
                       for target in ('ports-canary','descriptors-canary'))
        except (OSError,RuntimeError,json.JSONDecodeError):return False
    wait(ready,seconds=10)
    key=Path('/etc/platform-healer/node.key').read_bytes()
    policy=json.loads(Path('/etc/platform-healer/policy.json').read_text())
    targets={p['id']:dict(p,client=client,key=key,lease=15) for p in policy['targets']}
    knowledge=Knowledge(str(root/'knowledge.db'));engine=Engine(knowledge,targets)
    host_before=Path('/proc/sys/net/ipv4/ip_local_port_range').read_text()
    evidence={'started':time.time(),'host_range_before':host_before,'runs':[]}
    controls={p['id']:Path('/run/platform-healer/fixtures')/p['kind']/'desired' for p in policy['targets']}
    def sample(target):return client.request('/sample/'+target)
    try:
        for occurrence in range(3):
            target='descriptors-canary';control=controls[target]
            before=sample(target)
            assert before['metrics']['soft_limit']==64
            engine.tick();control.write_text('128')
            wait(lambda:sample(target)['metrics']['allocation_errors']>before['metrics']['allocation_errors'])
            engine.tick()
            case=knowledge.export()['incidents'][-1]
            assert case['cause']=='process_descriptor_exhaustion'
            if occurrence<2:
                assert case['status']=='pending'
                engine.approve(case['id'],'lab-operator','Reviewed actual EMFILE and bounded per-process ceiling')
            else:
                assert knowledge.authorised(case)
            time.sleep(.6);engine.tick()
            def verified():
                engine.tick()
                return next(c for c in knowledge.export()['incidents'] if c['id']==case['id'])['status']=='verified'
            wait(verified)
            after=sample(target)
            assert before['identity']==after['identity']
            assert after['metrics']['held_fds']==128
            evidence['runs'].append(dict(kind='descriptors',occurrence=occurrence+1,
                decision='reviewed' if occurrence<2 else 'learned',before=before,after=after,time=time.time()))
            control.write_text('0')
            wait(lambda:sample(target)['metrics']['held_fds']==0)
            wait(lambda:sample(target)['metrics']['soft_limit']==64,seconds=20)
            if occurrence==1:
                engine.promote(case['scope'],case['cause'],case['action'],'lab-operator')
        target='ports-canary';before=sample(target);engine.tick();controls[target].write_text('96')
        wait(lambda:sample(target)['metrics']['allocation_errors']>before['metrics']['allocation_errors'])
        engine.tick();case=knowledge.export()['incidents'][-1]
        assert case['cause']=='outbound_port_exhaustion'
        engine.approve(case['id'],'lab-operator','Reviewed EADDRNOTAVAIL in loopback-only network namespace')
        time.sleep(.6);engine.tick()
        def network_verified():
            engine.tick()
            return next(c for c in knowledge.export()['incidents'] if c['id']==case['id'])['status']=='verified'
        wait(network_verified)
        after=sample(target)
        assert before['identity']==after['identity']
        evidence['runs'].append(dict(kind='ports',before=before,after=after,time=time.time()))
    finally:
        for control in controls.values():control.write_text('0')
        evidence['finished']=time.time();evidence['knowledge']=engine.snapshot()
        evidence['host_range_after']=Path('/proc/sys/net/ipv4/ip_local_port_range').read_text()
        (root/'evidence.json').write_text(json.dumps(evidence,indent=2))
        print('Private evidence:',root/'evidence.json',flush=True)
    assert evidence['host_range_before']==evidence['host_range_after']
    wait(lambda:sample('ports-canary')['metrics']['range']==[40000,40031],seconds=20)
    print('PASS: three descriptor occurrences, learned reuse, outbound-port repair, unchanged host range and rollback.',flush=True)

if __name__=='__main__':main()
