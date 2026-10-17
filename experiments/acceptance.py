"""Read-only post-deployment acceptance, except one deliberately invalid intent.

Run on the management host after draining load and finishing the native workflow.
It does not inject another fault or make a valid mutation.
"""
import json,sys,urllib.error,urllib.parse,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from deploy_lab import Admin,ROOT


def get(url):
    with urllib.request.urlopen(url,timeout=10) as response:return json.load(response)


def query(expression):
    result=get('http://10.1.1.50:9090/api/v1/query?'+urllib.parse.urlencode({'query':expression}))
    assert result['status']=='success'
    return result['data']['result']


def main():
    admin=Admin(json.loads((ROOT/'config/educloud.json').read_text()))
    targets=get('http://10.1.1.50:9090/api/v1/targets')['data']['activeTargets']
    assert len(targets)==10 and all(t['health']=='up' for t in targets)
    assert len(query('platform_sample_fresh == 1'))==2
    assert len(query('platform_controller_loop_fresh == 1'))==1
    assert len(query('platform_resource_soft_limit == 64'))==1
    assert len(query('platform_resource_range_size == 32'))==1
    assert len(query('platform_resource_held_fds == 0'))==1
    assert len(query('platform_resource_active_connections == 0'))==1
    assert len(query('{__name__=~"platform_resource_(open_fds|soft_limit|held_fds)"}'))==3
    dashboard=json.loads((ROOT/'monitoring/dashboard.json').read_text())
    for panel in dashboard['panels']:
        assert query(panel['targets'][0]['expr']), 'No data for '+panel['title']
    assert get('http://127.0.0.1:8085/healthz')['loop_fresh'] is True
    try:get('http://127.0.0.1:8085/api/status')
    except urllib.error.HTTPError as exc:assert exc.code==401
    else:raise AssertionError('Unauthenticated incident access accepted')
    invalid=urllib.request.Request('http://10.1.1.80:30919/execute',data=b'{}',headers={'Content-Type':'application/json'})
    try:urllib.request.urlopen(invalid,timeout=10)
    except urllib.error.HTTPError as exc:assert exc.code==409
    else:raise AssertionError('Unsigned action accepted')
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
    print('PASS: 10 healthy scrape targets, 10 populated dashboard panels, fresh samples, baseline rollback, unauthenticated/unsigned refusal, 3 Ready nodes, 2 non-root runtime Pods and obsolete namespace absent.')

if __name__=='__main__':main()
