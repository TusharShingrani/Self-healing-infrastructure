"""Read-only route/packet evidence for the one required private forwarding source."""
import concurrent.futures,urllib.request,time
from expansion import transport
control=transport('k8s-control')
ok,out,err=control._probe('ip -4 address show flannel.1; ip -4 route get 10.42.1.4; command -v tcpdump || true')
print(out,err)
worker=transport('k8s-worker-1')
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
    future=pool.submit(worker._probe,'sudo timeout 8 tcpdump -nni flannel.1 -c 3 "tcp and dst port 8080 and src host 10.42.0.0"')
    time.sleep(1)
    for _ in range(4):
        try:
            with urllib.request.urlopen('http://10.1.1.80:30080/readyz',timeout=1) as response:response.read(128)
        except OSError:pass
    ok,out,err=future.result();print('Packet source evidence:',out,err)
worker=transport('k8s-worker-1')
ok,out,err=worker._probe('command -v tcpdump || true; sudo iptables -L KUBE-ROUTER-FORWARD -n -v | head -10')
print(out,err)
