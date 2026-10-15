"""TLS-verified, namespace-bound Kubernetes client; no arbitrary command interface."""
import base64,json,ssl,urllib.request,urllib.error,urllib.parse
from pathlib import Path

class KubernetesError(RuntimeError):pass

class Kubernetes:
    def __init__(self,path=None,namespace='jobs-lab'):
        if namespace!='jobs-lab':raise ValueError('Namespace outside capability scope')
        config=json.loads(Path(path or Path.home()/'.config/healer-jobs/kube.json').read_text())
        if config['url']!='https://10.1.1.80:6443':raise ValueError('Unexpected API endpoint')
        self.url=config['url'];self.token=config['token'];self.namespace=namespace
        self.ssl=ssl.create_default_context(cadata=base64.b64decode(config['ca']).decode())

    def request(self,path,data=None):
        if '..' in path or '%2e' in path.lower() or '%2f' in path.lower():raise KubernetesError('Encoded/traversal path refused')
        if not path.startswith(('/api/v1/namespaces/jobs-lab/','/apis/apps/v1/namespaces/jobs-lab/',
                                '/apis/networking.k8s.io/v1/namespaces/jobs-lab/',
                                '/apis/metrics.k8s.io/v1beta1/namespaces/jobs-lab/','/api/v1/nodes/k8s-')) and path not in ('/metrics','/api/v1/namespaces/jobs-lab'):
            raise KubernetesError('Request outside lab scope')
        method='GET' if data is None else 'PATCH'
        headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/merge-patch+json' if data is not None else 'application/json'}
        request=urllib.request.Request(self.url+path,data=None if data is None else json.dumps(data).encode(),headers=headers,method=method)
        try:
            with urllib.request.urlopen(request,context=self.ssl,timeout=6) as response:
                raw=response.read(1048576).decode();return raw if path=='/metrics' or '/proxy/' in path else json.loads(raw)
        except urllib.error.HTTPError as error:raise KubernetesError('Kubernetes request refused: HTTP '+str(error.code)) from None
        except (OSError,ValueError):raise KubernetesError('Kubernetes response unreadable or API unavailable') from None

    def resource(self,kind,name,data=None):
        allowed={'deployments':{'job-api','job-worker','job-policy-witness'},'configmaps':{'job-settings'},
                 'networkpolicies':{'job-default-deny','job-api-ingress','job-metrics-ingress','job-witness-ingress','job-database-egress'}}
        if kind not in allowed or name not in allowed[kind]:raise KubernetesError('Resource outside capability allowlist')
        prefix='/apis/apps/v1' if kind=='deployments' else '/apis/networking.k8s.io/v1' if kind=='networkpolicies' else '/api/v1'
        return self.request(prefix+'/namespaces/jobs-lab/'+kind+'/'+name,data)

    def pods(self):return self.request('/api/v1/namespaces/jobs-lab/pods')['items']
    def policies(self):return self.request('/apis/networking.k8s.io/v1/namespaces/jobs-lab/networkpolicies')['items']
    def node(self,name):
        if name not in ('k8s-control','k8s-worker-1','k8s-worker-2'):raise KubernetesError('Node outside observation scope')
        return self.request('/api/v1/nodes/'+name)
