"""Bounded connection-holding load from the independent benchmark VM only."""
import argparse,http.client,json,re,secrets,socket,threading,time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=18);parser.add_argument('--concurrency',type=int,default=64);parser.add_argument('--name',required=True);parser.add_argument('--record-events',action='store_true');args=parser.parse_args()
    if socket.gethostname()!='probe-1' or not 5<=args.seconds<=30 or not 1<=args.concurrency<=80 or not re.fullmatch('[a-z0-9-]{1,64}',args.name):raise ValueError('Unqualified load origin, bound or output name')
    root=Path('/var/tmp/platform-gateway-results');root.mkdir(mode=0o700,exist_ok=True)
    lock=threading.Lock();stop=threading.Event();active=set();counts={'completed':0,'http_error':0,'connection_error':0,'cancelled':0};started=time.time();events=[];dropped=0
    def worker():
        nonlocal dropped
        while not stop.is_set():
            connection=http.client.HTTPConnection('10.203.0.2',18080,timeout=35)
            with lock:active.add(connection)
            result='connection_error';attempt=time.time();sent=None;status=0;error=''
            try:
                nonce=secrets.token_hex(12)
                connection.request('GET','/hold?seconds=25&nonce='+nonce,headers={'Connection':'close'})
                sent=time.time();response=connection.getresponse();status=response.status;body=response.read(4097)
                result='completed' if response.status==200 and body==('gateway-ok:'+nonce+'\n').encode() else 'http_error'
            except (OSError,http.client.HTTPException) as exc:result='cancelled' if stop.is_set() else 'connection_error';error=type(exc).__name__
            finally:
                with lock:
                    active.discard(connection);counts[result]+=1
                    if args.record_events:
                        if len(events)<8192:events.append({'started':attempt,'sent':sent,'finished':time.time(),'result':result,'status':status,'error_type':error})
                        else:dropped+=1
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
    output={'started':started,'finished':time.time(),'seconds':args.seconds,'concurrency':args.concurrency,'outcomes':counts}
    if args.record_events:output.update(events=events,events_dropped=dropped,threads_alive=sum(t.is_alive() for t in threads))
    (root/(args.name+'.json')).write_text(json.dumps(output))


if __name__=='__main__':main()
