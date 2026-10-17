"""Read-only post-deployment acceptance, except one deliberately invalid intent.

Run on the management host after draining load and finishing the native workflow.
It does not inject another fault or make a valid mutation.
"""
import json,sys,ssl,time,urllib.error,urllib.parse,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from deploy_lab import Admin,ROOT


def get(url):
    deadline=time.monotonic()+30
    while True:
        try:
            with urllib.request.urlopen(url,timeout=10) as response:return json.load(response)
        except urllib.error.HTTPError:raise
        except (urllib.error.URLError,OSError):
            if time.monotonic()>=deadline:raise
            time.sleep(1)


def query(expression):
    result=get('http://10.1.1.50:9090/api/v1/query?'+urllib.parse.urlencode({'query':expression}))
    assert result['status']=='success'
    return result['data']['result']


def main():
    admin=Admin(json.loads((ROOT/'config/educloud.json').read_text()))
    deadline=time.monotonic()+60
    while True:
        targets=get('http://10.1.1.50:9090/api/v1/targets')['data']['activeTargets']
        if len(targets)==11 and all(t['health']=='up' for t in targets):break
        if time.monotonic()>=deadline:break
        time.sleep(2)
    assert len(targets)==11 and all(t['health']=='up' for t in targets),[(t['labels'].get('job'),t['health']) for t in targets]
    assert len(query('platform_sample_fresh == 1'))==1
    assert len(query('platform_controller_loop_fresh == 1'))==1
    assert len(query('platform_resource_range_size == 32'))==1
    assert len(query('platform_resource_active_connections == 0'))==1
    assert len(query('platform_resource_client_transaction_ok == 1'))==1
    assert len(query('platform_resource_upstream_healthy == 1'))==1
    dashboard=json.loads((ROOT/'monitoring/dashboard.json').read_text())
    for panel in dashboard['panels']:
        assert query(panel['targets'][0]['expr']), 'No data for '+panel['title']
    assert get('http://127.0.0.1:8085/healthz')['loop_fresh'] is True
    try:get('http://127.0.0.1:8085/api/status')
    except urllib.error.HTTPError as exc:assert exc.code==401
    else:raise AssertionError('Unauthenticated incident access accepted')
    pki=Path.home()/'.config/platform-healer/pki'
    url='https://10.1.1.80:30919'
    for role,expected in [('monitor',403),('controller',409)]:
        context=ssl.create_default_context(cafile=str(pki/'ca.crt'))
        context.load_cert_chain(str(pki/(role+'.crt')),str(pki/(role+'.key')))
        invalid=urllib.request.Request(url+'/execute',data=b'{}',headers={'Content-Type':'application/json'})
        try:urllib.request.urlopen(invalid,timeout=10,context=context)
        except urllib.error.HTTPError as exc:assert exc.code==expected
        else:raise AssertionError('Read-only or unsigned action accepted')
        with urllib.request.urlopen(url+'/sample/gateway-ports',context=context,timeout=10) as response:
            sample=json.load(response)
        assert not sample['error'] and sample['metrics']['client_transaction_ok']
    context=ssl.create_default_context(cafile=str(pki/'ca.crt'))
    try:urllib.request.urlopen(url+'/targets',context=context,timeout=5)
    except (urllib.error.URLError,ssl.SSLError,ConnectionError):pass
    else:raise AssertionError('Missing client certificate accepted')
    nodes=json.loads(admin.run('k8s-control','sudo k3s kubectl get nodes -o json'))['items']
    assert len(nodes)==3 and all(any(c['type']=='Ready' and c['status']=='True' for c in node['status']['conditions']) for node in nodes)
    for namespace in ('platform-healer','platform-healer-system'):
        pods=json.loads(admin.run('k8s-control','sudo k3s kubectl -n '+namespace+' get pods -o json'))['items']
        assert len(pods)==1
        pod=pods[0]
        assert all(c['ready'] for c in pod['status']['containerStatuses'])
        assert pod['spec'].get('automountServiceAccountToken') is False
        for container in pod['spec']['containers']:
            security=container['securityContext']
            assert security['allowPrivilegeEscalation'] is False and security['readOnlyRootFilesystem'] is True
            assert security['capabilities']['drop']==['ALL']
        permission=admin.run('k8s-control','sudo k3s kubectl auth can-i delete nodes --as=system:serviceaccount:'+namespace+':platform-healer || true').decode().strip()
        assert permission=='no'
    namespaces=json.loads(admin.run('k8s-control','sudo k3s kubectl get namespaces -o json'))['items']
    assert not any(n['metadata']['name']=='jobs-lab' for n in namespaces)
    print('PASS: 11 healthy scrape targets, all gateway dashboard panels populated, baseline rollback, fresh independent transactions, mTLS client requirement, monitor write refusal, unsigned intent refusal, 3 Ready nodes, 2 constrained runtime Pods and obsolete namespace absent.')

if __name__=='__main__':main()
