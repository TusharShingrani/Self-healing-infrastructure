#!/usr/bin/env python3
"""Small request-concurrency/monitoring-overhead sweep, not a node-scale claim."""
import concurrent.futures
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from infrastructure import build


def request(_):
    start=time.monotonic()
    try:
        with urllib.request.urlopen('http://10.1.1.60:8088/healthz',timeout=8) as r:
            data=json.loads(r.read());ok=r.status==200 and data.get('healthy') is True
    except urllib.error.HTTPError as error:
        try:data=json.loads(error.read())
        except ValueError:data={'error':'invalid diagnostic response'}
        return {'ok':False,'ms':(time.monotonic()-start)*1000,'diagnostic':data}
    except (OSError,ValueError):ok=False
    return {'ok':ok,'ms':(time.monotonic()-start)*1000}


def main():
    w,o,h=build();before=w.observe(False)
    if not w.health(before):raise RuntimeError('Baseline unhealthy')
    result={'started':time.time(),'duration_per_cell_seconds':20,'scope':'one transaction across two VMs; request concurrency, not managed-node scalability','cells':[]}
    try:
        # Alternate phase order to reduce a simple warm-up ordering bias.
        for concurrency in (1,4,8):
            phases=('off','on') if concurrency!=4 else ('on','off')
            for phase in phases:
                subprocess.run(['systemctl','--user','start' if phase=='on' else 'stop','healer-infrastructure'],check=True)
                time.sleep(2)
                def metrics():
                    if phase=='off':return {}
                    with urllib.request.urlopen('http://10.1.1.205:9106/metrics',timeout=10) as response:
                        return {line.split()[0]:float(line.split()[1]) for line in response.read().decode().splitlines() if '{' not in line}
                metrics_before=metrics()
                start=time.monotonic();deadline=start+20
                def worker(_):
                    samples=[]
                    while time.monotonic()<deadline:samples.append(request(None))
                    return samples
                with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                    groups=list(pool.map(worker,range(concurrency)))
                    samples=[s for group in groups for s in group]
                elapsed=time.monotonic()-start;times=sorted(s['ms'] for s in samples)
                cell={'concurrency':concurrency,'monitoring':phase,'elapsed_seconds':elapsed,'requests':len(samples),'successful':sum(s['ok'] for s in samples),
                      'requests_per_second':len(samples)/elapsed,'p50_ms':times[int(.5*(len(times)-1))],'p95_ms':times[int(.95*(len(times)-1))],'p99_ms':times[int(.99*(len(times)-1))],'samples':samples}
                metrics_after=metrics()
                cell['monitor_metrics_before']=metrics_before;cell['monitor_metrics_after']=metrics_after
                if phase=='on':
                    cell['observed_monitor_ticks']=metrics_after['healer_infrastructure_ticks_total']-metrics_before['healer_infrastructure_ticks_total']
                    cell['monitor_cpu_seconds']=metrics_after['healer_infrastructure_process_cpu_seconds']-metrics_before['healer_infrastructure_process_cpu_seconds']
                    if cell['observed_monitor_ticks']<1:raise RuntimeError('No monitoring cycle overlapped the active phase')
                result['cells'].append(cell);print(json.dumps({k:v for k,v in cell.items() if k!='samples'}),flush=True)
        result['healthy_after']=w.health(w.observe(False));result['resources']=w.diagnostic_evidence()
        # Neither test prints or stores the cache passwords.
        ok,out,err=w.command('app-2','redis-cli -p 6380 PING')
        result['unauthenticated_cache_refused']='NOAUTH' in out
        # Run as the canary identity and prove administrative capability denied.
        code="import sys;sys.path.insert(0,'/opt/healer-stack');from transaction import redis_command;\ntry: redis_command('10.1.1.61','CONFIG','GET','maxmemory');print('UNEXPECTED_ALLOWED')\nexcept ValueError as e: print('DENIED' if 'NOPERM' in str(e) else 'OTHER_FAILURE')"
        import shlex
        ok,out,err=w.command('app-1','sudo -u healer-stack python3 -c '+shlex.quote(code))
        result['canary_admin_refused']=ok and out=='DENIED'
        result['finished']=time.time();Path('evidence/infrastructure-benchmark.json').write_text(json.dumps(result,indent=2)+'\n')
    finally:
        subprocess.run(['systemctl','--user','start','healer-infrastructure'],check=True)


if __name__=='__main__':main()
