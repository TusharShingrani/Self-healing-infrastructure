"""Unprivileged node agent; forwards signed intents but cannot mint one."""
import argparse,json,time,threading
from http.server import BaseHTTPRequestHandler,HTTPServer
from .transport import UnixClient
from .model import canonical
from .tls import MutualHTTPServer,peer_name

def main():
    p=argparse.ArgumentParser();p.add_argument('--socket',default='/run/platform-healer/broker.sock');p.add_argument('--port',type=int,default=9119);p.add_argument('--tls',default='/run/tls');a=p.parse_args();client=UnixClient(a.socket)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):super().setup();self.connection.settimeout(5)
        def reply(self,status,data):
            body=canonical(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_GET(self):
            try:
                if self.path=='/healthz':
                    client.request('/targets');return self.reply(200,{'agent_alive':True,'broker_reachable':True})
                if self.path=='/metrics':
                    try:targets=client.request('/targets')['targets'];up=1
                    except Exception:targets=[];up=0
                    lines=[f'platform_agent_broker_up {up}',f'platform_agent_targets {len(targets)}']
                    try:
                        journal=client.request('/leases')
                        lines.append('platform_broker_refused_operations_total '+str(journal['refusals']))
                        for status,count in journal['counts'].items():
                            lines.append(f'platform_broker_operations{{status="{status}"}} {count}')
                    except Exception:lines.append('platform_broker_journal_readable 0')
                    for target in targets:
                        try:
                            sample=client.request('/sample/'+target)
                            from .model import Sample
                            fresh=Sample(**sample).valid()
                            lines.append(f'platform_sample_fresh{{target="{target}"}} {int(fresh)}')
                            for name,value in sample['metrics'].items():
                                if type(value) in (int,float,bool):lines.append(f'platform_resource_{name}{{target="{target}"}} {int(value) if type(value)is bool else value}')
                        except Exception:lines.append(f'platform_sample_fresh{{target="{target}"}} 0')
                    body=('\n'.join(lines)+'\n').encode();self.send_response(200);self.send_header('Content-Type','text/plain; version=0.0.4');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
                if self.path=='/targets' or any(self.path.startswith(x) for x in ('/sample/','/verify/','/operation/')):return self.reply(200,client.request(self.path))
                self.reply(404,{'error':'Unknown agent route'})
            except Exception as exc:self.reply(503,{'error':str(exc)[:200]})
        def do_POST(self):
            try:
                if peer_name(self.connection)!='platform-controller':return self.reply(403,{'error':'This TLS identity has read-only access'})
                if self.path!='/execute':return self.reply(404,{'error':'Unknown agent route'})
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=16384 or self.headers.get('Transfer-Encoding'):raise ValueError('Bounded request required')
                self.reply(200,client.request('/execute',json.loads(self.rfile.read(size))))
            except Exception as exc:self.reply(409,{'error':str(exc)[:200]})
        def log_message(self,*args):pass
    class Health(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path!='/healthz':self.send_error(404);return
            try:client.request('/targets');status=200
            except Exception:status=503
            self.send_response(status);self.end_headers()
        def log_message(self,*args):pass
    threading.Thread(target=HTTPServer(('0.0.0.0',9120),Health).serve_forever,daemon=True).start()
    MutualHTTPServer(('0.0.0.0',a.port),Handler,a.tls).serve_forever()
if __name__=='__main__':main()
