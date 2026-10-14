#!/usr/bin/env python3
"""Independent reviewed MAPE-K dependency loop with read-only observability."""
import json
import os
import resource
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from infrastructure import build


def main():
    world, operator, healer = build()
    lock=threading.Lock();stop=threading.Event();snapshot={};ticks=errors=0
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            with lock:
                cases=operator.cases();procedures=operator.procedures()
                if self.path=='/metrics':
                    obs=snapshot.get('observation',{})
                    lines=[f'healer_infrastructure_healthy {int(world.health(obs))}',
                           f'healer_infrastructure_ticks_total {ticks}', f'healer_infrastructure_errors_total {errors}',
                           f'healer_infrastructure_pending {sum(c["status"]=="pending" for c in cases)}',
                           f'healer_infrastructure_validated {sum(p["status"]=="validated" for p in procedures)}',
                           f'healer_infrastructure_advisor_available {int(healer.advisor is not None and healer.advisor.available)}',
                           f'healer_infrastructure_advisor_pending {healer.knowledge.counts()["advice"].get("pending",0)}',
                           f'healer_infrastructure_tick_seconds {snapshot.get("tick_seconds",0)}',
                           f'healer_infrastructure_process_cpu_seconds {resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime}',
                           f'healer_infrastructure_last_tick_seconds {snapshot.get("time",0)}',
                           f'healer_infrastructure_transaction_ms {obs.get("transaction",{}).get("latency_ms",0)}']
                    for name, value in obs.get('infrastructure_checks',{}).items():
                        lines.append(f'healer_infrastructure_check{{check="{name}"}} {int(value) if type(value) is bool else -1}')
                    body=('\n'.join(lines)+'\n').encode();kind='text/plain; version=0.0.4'
                elif self.path=='/status':
                    body=json.dumps(dict(snapshot,cases=cases,procedures=procedures)).encode();kind='application/json'
                else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('10.1.1.205',9106),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    signal.signal(signal.SIGTERM,lambda *args:stop.set());signal.signal(signal.SIGINT,lambda *args:stop.set())
    while not stop.is_set():
        start=time.monotonic()
        with lock:
            try:
                healer.knowledge.expire_advice()
                healer.config='A' if os.path.exists('state/infrastructure/paused') else 'C'
                healer.tick();ticks+=1
                snapshot={'time':time.time(),'observation':world.latest,'events':[e.__dict__ for e in healer.events[-1:]],'tick_seconds':time.monotonic()-start}
                with open('state/infrastructure/events.jsonl','a') as out:out.write(json.dumps(snapshot)+'\n')
                print(json.dumps(snapshot),flush=True)
            except Exception as error:
                errors+=1;print(type(error).__name__+': '+str(error)[:500],flush=True)
        stop.wait(max(0,10-(time.monotonic()-start)))
    server.shutdown()


if __name__=='__main__':main()
