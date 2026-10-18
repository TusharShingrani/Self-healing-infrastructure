"""Bounded connection-holding load from the independent benchmark VM only."""
import argparse,http.client,json,re,secrets,socket,threading,time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=18);parser.add_argument('--concurrency',type=int,default=64);parser.add_argument('--name',required=True);args=parser.parse_args()
    if socket.gethostname()!='probe-1' or not 5<=args.seconds<=30 or not 1<=args.concurrency<=80 or not re.fullmatch('[a-z0-9-]{1,64}',args.name):raise ValueError('Unqualified load origin, bound or output name')
    root=Path('/var/tmp/platform-gateway-results');root.mkdir(mode=0o700,exist_ok=True)
    lock=threading.Lock();stop=threading.Event();active=set();counts={'completed':0,'http_error':0,'connection_error':0,'cancelled':0};started=time.time()
    def worker():
        while not stop.is_set():
            connection=http.client.HTTPConnection('10.203.0.2',18080,timeout=35)
            with lock:active.add(connection)
            result='connection_error'
            try:
                nonce=secrets.token_hex(12)
                connection.request('GET','/hold?seconds=25&nonce='+nonce,headers={'Connection':'close'})
                response=connection.getresponse();body=response.read(4097)
                result='completed' if response.status==200 and body==('gateway-ok:'+nonce+'\n').encode() else 'http_error'
            except (OSError,http.client.HTTPException):result='cancelled' if stop.is_set() else 'connection_error'
            finally:
                with lock:active.discard(connection);counts[result]+=1
                connection.close()
            stop.wait(.5)
    threads=[threading.Thread(target=worker,daemon=True) for _ in range(args.concurrency)]
    for thread in threads:thread.start()
    stop.wait(args.seconds);stop.set()
    with lock:connections=list(active)
    for connection in connections:
        try:
            if connection.sock:connection.sock.shutdown(socket.SHUT_RDWR)
        except OSError:pass
        connection.close()
    for thread in threads:thread.join(.05)
    (root/(args.name+'.json')).write_text(json.dumps({'started':started,'finished':time.time(),'seconds':args.seconds,'concurrency':args.concurrency,'outcomes':counts}))


if __name__=='__main__':main()
