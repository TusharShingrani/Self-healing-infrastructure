"""Independent, non-mutating client on the benchmark VM."""
import json,secrets,threading,time,urllib.request,urllib.error,argparse
from collections import deque
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from .tls import MutualHTTPServer
from .transport import fixed_opener

TARGET='http://10.203.0.2:18080'


def check():
    nonce=secrets.token_hex(12);start=time.monotonic();success=False;status=0
    try:
        with fixed_opener().open(TARGET+'/transaction?nonce='+nonce,timeout=1) as response:
            status=response.status;success=status==200 and response.read(4097)==('gateway-ok:'+nonce+'\n').encode()
    except urllib.error.HTTPError as exc:status=exc.code
    except OSError:pass
    return {'time':time.time(),'target':TARGET,'success':success,'status':status,'latency_seconds':time.monotonic()-start}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--tls',default='/etc/platform-observer-tls');args=parser.parse_args()
    lock=threading.Lock();latest={};counts={'success':0,'failure':0};history=deque(maxlen=120)
    def loop():
        while True:
            value=check()
            with lock:latest.clear();latest.update(value);history.append(value);counts['success' if value['success'] else 'failure']+=1
            time.sleep(1)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):super().setup();self.connection.settimeout(3)
        def do_GET(self):
            with lock:value=dict(latest);counter=dict(counts);recent=list(history)
            if self.path=='/status':body=json.dumps(value).encode();kind='application/json'
            elif self.path=='/history':body=json.dumps(recent).encode();kind='application/json'
            elif self.path=='/metrics':
                body=('platform_gateway_transaction_success '+str(int(value.get('success',False)))+'\nplatform_gateway_transaction_latency_seconds '+str(value.get('latency_seconds',0))+'\nplatform_gateway_observation_time '+str(value.get('time',0))+'\n'+''.join('platform_gateway_client_checks_total{outcome="'+key+'"} '+str(count)+'\n' for key,count in counter.items())).encode();kind='text/plain; version=0.0.4'
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    threading.Thread(target=loop,daemon=True).start()
    MutualHTTPServer(('10.1.1.84',9106),Handler,args.tls).serve_forever()


if __name__=='__main__':main()
