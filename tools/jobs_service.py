"""Reviewed job MAPE-K service; read-only completed-tick snapshots on 9109."""
import json,os,signal,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from jobs import build

def main():
    world,op,h=build();stop=threading.Event();published={'metrics':'job_healer_snapshot_ready 0\n','status':b'{}'};ticks=errors=0
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            view=published
            if self.path=='/metrics':body=view['metrics'].encode();kind='text/plain'
            elif self.path=='/status':body=view['status'];kind='application/json'
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('10.1.1.205',9109),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    signal.signal(signal.SIGTERM,lambda *args:stop.set());signal.signal(signal.SIGINT,lambda *args:stop.set())
    while not stop.is_set():
        start=time.monotonic()
        try:
            h.knowledge.expire_advice();h.config='A' if os.path.exists('state/jobs/paused') else 'C';h.tick();ticks+=1
            cases=op.cases();procedures=op.procedures();obs=world.latest
            snapshot={'time':time.time(),'paused':h.config=='A','observation':obs,'tick_seconds':time.monotonic()-start,
                      'cases':[{k:c[k] for k in ('id','cause','status','procedure_id')} for c in cases[:20]],'procedures':procedures,'events':[e.__dict__ for e in h.events[-1:]]}
            _,current_scope=op.context(world,[], 'unknown',[],obs)
            values={'healthy':int(world.health(obs)),'paused':int(h.config=='A'),'business_healthy':int(obs.get('http_ok') is True),'ticks_total':ticks,'errors_total':errors,
                    'last_tick_seconds':snapshot['time'],'tick_seconds':snapshot['tick_seconds'],'pending':sum(c['status']=='pending' for c in cases),
                    'validated':sum(p['status']=='validated' and p['scope']==current_scope for p in procedures),'advisor_available':int(h.advisor is not None and h.advisor.available),
                    'advisor_pending':h.knowledge.counts()['advice'].get('pending',0)}
            metrics=[f'job_healer_{k} {v}' for k,v in values.items()]
            metrics += [f'job_healer_check{{check="{name}"}} {int(value) if type(value) is bool else -1}' for name,value in obs['infrastructure_checks'].items()]
            for name,d in obs.get('deployments',{}).items():
                metrics += [f'job_kubernetes_replicas{{deployment="{name}",state="{state}"}} {d[state]}' for state in ('desired','ready')]
            for pod in obs.get('pods',[]):metrics.append(f'job_kubernetes_pod_restarts{{pod="{pod["name"]}",node="{pod["node"]}"}} {pod["restarts"]}')
            try:
                server_metrics=world.kube.request('/metrics')
                totals={k:0.0 for k in ('apiserver_request_total','apiserver_request_duration_seconds_sum','apiserver_request_duration_seconds_count')}
                for line in server_metrics.splitlines():
                    name=line.split('{',1)[0].split(' ',1)[0]
                    if name in totals:totals[name]+=float(line.split()[-1])
                metrics += [f'job_kubernetes_{name} {value}' for name,value in totals.items()]
                usage=world.kube.request('/apis/metrics.k8s.io/v1beta1/namespaces/jobs-lab/pods')
                for pod in usage.get('items',[]):
                    for container in pod.get('containers',[]):
                        cpu=container['usage']['cpu'];memory=container['usage']['memory']
                        cores=float(cpu[:-1])/1e9 if cpu.endswith('n') else float(cpu[:-1])/1000 if cpu.endswith('m') else float(cpu)
                        mib=float(memory[:-2])/1024 if memory.endswith('Ki') else float(memory[:-2]) if memory.endswith('Mi') else float(memory)/1048576
                        labels=f'pod="{pod["metadata"]["name"]}",container="{container["name"]}"'
                        metrics += [f'job_pod_cpu_cores{{{labels}}} {cores}',f'job_pod_memory_mib{{{labels}}} {mib}']
                metrics.append('job_kubernetes_metrics_available 1')
            except (RuntimeError,ValueError,KeyError):metrics.append('job_kubernetes_metrics_available 0')
            # Read metrics through the API proxy; no pod-network route is installed on monitor.
            for pod in obs.get('pods',[]):
                if pod['phase']!='Running' or pod['name'].startswith('job-policy-witness'):continue
                try:
                    text=world.kube.request('/api/v1/namespaces/jobs-lab/pods/'+pod['name']+':8080/proxy/metrics')
                    for line in text.splitlines():
                        parts=line.split()
                        if len(parts)==2 and parts[0].startswith('job_process_'):
                            value=float(parts[1]);metrics.append(f'{parts[0]}{{pod="{pod["name"]}"}} {value}')
                except (RuntimeError,ValueError):metrics.append(f'job_pod_metrics_unreadable{{pod="{pod["name"]}"}} 1')
            published={'metrics':'\n'.join(metrics)+'\n','status':json.dumps(snapshot).encode()}
            with open('state/jobs/events.jsonl','a') as file:file.write(json.dumps(snapshot)+'\n')
            print(json.dumps({'time':snapshot['time'],'healthy':world.health(obs),'checks':obs['infrastructure_checks'],'events':snapshot['events']}),flush=True)
        except (RuntimeError,OSError,ValueError,KeyError) as error:
            errors+=1;print('job loop error: '+type(error).__name__+': '+str(error)[:300],flush=True)
        stop.wait(max(0,10-(time.monotonic()-start)))
    server.shutdown()

if __name__=='__main__':main()
