"""Node-local Unix socket broker. Root service; never a public TCP listener."""
import argparse,json,os,socket,threading,time,logging,stat
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from .leases import Broker
from .plugins.linux import Ports,Descriptors
from .plugins.gateway import Gateway
from .model import canonical

class UnixServer(HTTPServer):
    address_family=socket.AF_UNIX
    def server_bind(self):self.socket.bind(self.server_address);self.server_name='localhost';self.server_port=0
    def get_request(self):
        connection,address=super().get_request();connection.settimeout(5);return connection,address

def main():
    p=argparse.ArgumentParser();p.add_argument('--policy',default='/etc/platform-healer/policy.json');p.add_argument('--key',default='/etc/platform-healer/node.key');p.add_argument('--state',default='/var/lib/platform-healer/journal.db');p.add_argument('--socket',default='/run/platform-healer/broker.sock');p.add_argument('--group',type=int,default=64532);a=p.parse_args()
    if os.geteuid()!=0:raise RuntimeError('Host broker must be installed by a node administrator')
    for filename in (a.policy,a.key):
        metadata=os.lstat(filename)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid!=0 or metadata.st_mode&0o077:
            raise ValueError('Policy and signing key must be root-owned private regular files')
    policy=json.loads(Path(a.policy).read_text());factories={'ports':Ports,'descriptors':Descriptors,'gateway_ports':Gateway};plugins={}
    for spec in policy['targets']:
        if spec['kind'] not in factories:raise ValueError('Unsupported mutation plugin')
        plugins[spec['id']]=factories[spec['kind']](spec)
    Path(a.state).parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    b=Broker(a.state,Path(a.key).read_bytes(),plugins)
    class Handler(BaseHTTPRequestHandler):
        def reply(self,status,data):
            body=canonical(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_GET(self):
            try:
                if self.path=='/targets':return self.reply(200,{'targets':list(plugins)})
                if self.path=='/leases':
                    with b.lock:
                        counts={r[0]:r[1] for r in b.db.execute('SELECT status,count(*) FROM operations GROUP BY status')}
                    return self.reply(200,{'counts':counts,'refusals':b.db.execute('SELECT count(*) FROM refusals').fetchone()[0]})
                if self.path.startswith('/sample/'):
                    target=self.path.removeprefix('/sample/')
                    if target not in plugins:raise ValueError('Unknown target')
                    return self.reply(200,plugins[target].sample().json())
                if self.path.startswith('/verify/'):
                    target=self.path.removeprefix('/verify/')
                    if target not in plugins:raise ValueError('Unknown target')
                    return self.reply(200,{'verified':plugins[target].verify(),'time':time.time()})
                if self.path.startswith('/operation/'):return self.reply(200,b.operation(self.path.removeprefix('/operation/')))
                self.reply(404,{'error':'Unknown broker route'})
            except Exception as exc:self.reply(409,{'error':type(exc).__name__+': '+str(exc)[:220]})
        def do_POST(self):
            try:
                if self.path!='/execute':return self.reply(404,{'error':'Unknown broker route'})
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=16384 or self.headers.get('Transfer-Encoding'):raise ValueError('Bounded request required')
                self.reply(200,b.execute(json.loads(self.rfile.read(size))))
            except Exception as exc:self.reply(409,{'error':type(exc).__name__+': '+str(exc)[:220]})
        def log_message(self,*args):pass
    def rollback():
        while True:
            try:b.reconcile()
            except Exception:logging.exception('Lease watchdog failed; operator intervention required')
            time.sleep(1)
    # Reconcile old intents before accepting new requests; absent fixtures defer visibly.
    b.reconcile(recover=True)
    threading.Thread(target=rollback,daemon=True).start()
    path=Path(a.socket);path.parent.mkdir(exist_ok=True,parents=True,mode=0o755)
    if path.exists():
        probe=socket.socket(socket.AF_UNIX)
        try:probe.connect(str(path))
        except OSError:path.unlink()
        else:raise RuntimeError('Another broker already owns this socket')
        finally:probe.close()
    server=UnixServer(str(path),Handler);os.chown(path,0,a.group);os.chmod(path,0o660);server.serve_forever()
if __name__=='__main__':main()
