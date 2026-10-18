"""Bounded live refusal checks after the gateway study has drained.

Only the owned namespace reservation and observer service are disturbed.
Never stress host memory or stop the protected control plane to test a refusal.
"""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from deploy_lab import Admin

def main():
    admin=Admin(json.loads((ROOT/'config/educloud.json').read_text()))
    program=r'''
import json,subprocess,time
from pathlib import Path
from platform_healer.model import intent
from platform_healer.transport import UnixClient
c=UnixClient('/run/platform-healer/broker.sock')
s=c.request('/sample/gateway-ports');assert not s['error']
assert s['metrics']['range']==[40000,40031] and s['metrics']['active_connections']==0
identity=s['identity'];key=Path('/etc/platform-healer/node.key').read_bytes()
prefix=['ip','netns','exec','platform-healer-gateway','sysctl']
old=subprocess.check_output(prefix+['-n','net.ipv4.ip_local_reserved_ports'],text=True).strip()
def reserved(value):subprocess.run(prefix+['-qw','net.ipv4.ip_local_reserved_ports='+value],check=True,stdin=subprocess.DEVNULL)
try:
    reserved(old+(',' if old else '')+'40100')
    s=c.request('/sample/gateway-ports');assert s['metrics']['reserved_conflict'] is True
    envelope=intent('gateway-ports',identity,'expand_port_range',[40000,40031],{'value':[40000,40255]},'Explicit live negative acceptance',key,lease=5)
    try:c.request('/execute',envelope)
    except Exception as exc:assert 'reserved' in str(exc).lower()
    else:raise AssertionError('Reserved-port conflict accepted')
finally:reserved(old)
try:c.request('/execute',envelope)
except Exception as exc:assert 'refused' in str(exc).lower()
else:raise AssertionError('Previously refused intent later executed')
assert c.request('/sample/gateway-ports')['metrics']['range']==[40000,40031]
try:
    subprocess.run(['systemctl','stop','platform-gateway-upstream'],check=True,stdin=subprocess.DEVNULL)
    envelope=intent('gateway-ports',identity,'expand_port_range',[40000,40031],{'value':[40000,40255]},'Explicit upstream outage refusal test',key,lease=5)
    try:c.request('/execute',envelope)
    except Exception as exc:assert 'upstream' in str(exc).lower()
    else:raise AssertionError('Upstream outage accepted port tuning')
finally:subprocess.run(['systemctl','start','platform-gateway-upstream'],check=True,stdin=subprocess.DEVNULL)
assert c.request('/sample/gateway-ports')['metrics']['range']==[40000,40031]
print(json.dumps({'reserved_conflict_refused':True,'refused_id_cannot_replay':True,'upstream_refused_by_root':True,'namespace_restored':True}))
'''
    result=json.loads(admin.run('k8s-worker-2','sudo env PYTHONPATH=/opt/platform-healer/src python3 -',program.encode()))
    try:
        admin.run('probe-1','sudo systemctl stop platform-gateway-observer')
        program='''
from pathlib import Path
from platform_healer.transport import UnixClient
from platform_healer.model import intent
c=UnixClient('/run/platform-healer/broker.sock');s=c.request('/sample/gateway-ports')
assert s['error'];assert s['metrics']['range']==[40000,40031]
envelope=intent('gateway-ports',s['identity'],'expand_port_range',[40000,40031],{'value':[40000,40255]},'Explicit missing observer refusal test',Path('/etc/platform-healer/node.key').read_bytes(),lease=5)
try:c.request('/execute',envelope)
except Exception as exc:assert 'telemetry' in str(exc).lower()
else:raise AssertionError('Unobservable target accepted a mutation')
assert c.request('/sample/gateway-ports')['metrics']['range']==[40000,40031]
print('missing observer is unknown and signed mutation refused')
'''
        import shlex
        admin.run('k8s-worker-2','sudo env PYTHONPATH=/opt/platform-healer/src python3 -c '+shlex.quote(program))
        result['missing_observer_unknown']=True
    finally:admin.run('probe-1','sudo systemctl start platform-gateway-observer')
    time.sleep(3)
    destination=Path.home()/'.local/state/platform-healer/evidence'/('gateway-safety-'+str(int(time.time()))+'.json')
    destination.write_text(json.dumps(result,indent=2));destination.chmod(0o600)
    print('PASS:',', '.join(result))

if __name__=='__main__':main()
