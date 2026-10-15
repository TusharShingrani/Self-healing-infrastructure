"""Bounded bootstrap diagnostics; never prints Kubernetes Secrets or join tokens."""
import urllib.request,urllib.error
from expansion import transport
node=transport('k8s-control')
for command in ('sudo k3s kubectl -n jobs-lab get deployments,pods,services,endpoints -o wide',
                'sudo k3s kubectl -n jobs-lab logs deployment/job-policy-witness --tail=10',
                'sudo iptables-save | grep -E "30080|30081|job-api|job-policy-witness"',
                'systemctl show k3s -p ExecStart; sudo k3s kubectl get nodes -o wide'):
    ok,out,err=node._probe(command);print(out,err)
for url in ('http://10.1.1.80:30080/readyz','http://10.1.1.81:30080/readyz','http://10.1.1.80:30081/status','http://10.1.1.84:9107/status'):
    try:
        with urllib.request.urlopen(url,timeout=4) as response:print(url,response.status,response.read(1500).decode())
    except OSError as error:print(url,type(error).__name__)
