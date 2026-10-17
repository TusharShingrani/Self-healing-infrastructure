"""Bounded infrastructure-only fixtures. No bank application and no external traffic."""
import argparse,errno,json,os,resource,selectors,socket,threading,time
from pathlib import Path

def start_time():return Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]
def main():
    p=argparse.ArgumentParser();p.add_argument('kind',choices=['ports','descriptors']);p.add_argument('--seconds',type=int,default=600);p.add_argument('--persistent',action='store_true',help='Keep the idle fixture alive; each load burst still expires after 120 seconds');a=p.parse_args()
    if not 10<=a.seconds<=900:raise ValueError('Fixture duration must be bounded to 10..900 seconds')
    root=Path('/run/platform-healer/fixtures')/a.kind;root.mkdir(parents=True,exist_ok=True,mode=0o700)
    identity={'pid':os.getpid(),'start_time':start_time(),'namespace_inode':os.stat('/proc/self/ns/net').st_ino}
    (root/'identity.json').write_text(json.dumps(identity));(root/'identity.json').chmod(0o600)
    control=root/'desired';control.write_text('0');control.chmod(0o600)
    cf=os.open(control,os.O_RDWR);sf=os.open(root/'status.json',os.O_CREAT|os.O_RDWR,0o600)
    held=[];errors=0;unexpected=0;desired=0;deadline=time.monotonic()+a.seconds;burst_deadline=None
    if a.kind=='descriptors':resource.setrlimit(resource.RLIMIT_NOFILE,(64,512))
    else:
        from .host_helper import read_ports
        if read_ports(19080)['range']!=[40000,40031]:raise RuntimeError('Refuse unprepared namespace')
        listen=socket.socket();listen.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);listen.bind(('127.0.0.1',19080));listen.listen(128);listen.setblocking(False)
        def echo():
            selector=selectors.DefaultSelector();selector.register(listen,selectors.EVENT_READ)
            while a.persistent or time.monotonic()<deadline:
                for key,_ in selector.select(.1):
                    s=key.fileobj
                    if s is listen:
                        conn,_=s.accept();conn.setblocking(False);selector.register(conn,selectors.EVENT_READ)
                    else:
                        try:
                            data=s.recv(1024)
                            if data:s.sendall(data)
                            else:selector.unregister(s);s.close()
                        except OSError:
                            selector.unregister(s);s.close()
        threading.Thread(target=echo,daemon=True).start()
    try:
        while a.persistent or time.monotonic()<deadline:
            try:desired=int(os.pread(cf,20,0).decode().strip())
            except (ValueError,OSError):pass
            if not 0<=desired<=128:desired=0
            if desired and burst_deadline is None:burst_deadline=time.monotonic()+120
            if desired and time.monotonic()>=burst_deadline:
                desired=0;os.pwrite(cf,b'0',0);os.ftruncate(cf,1)
            if not desired:burst_deadline=None
            while len(held)>desired:
                old=held.pop();os.close(old) if a.kind=='descriptors' else old.close()
            for _ in range(min(8,desired-len(held))):
                try:held.append(os.open('/dev/null',os.O_RDONLY) if a.kind=='descriptors' else socket.create_connection(('127.0.0.1',19080),timeout=.2))
                except OSError as exc:
                    if exc.errno==(errno.EMFILE if a.kind=='descriptors' else errno.EADDRNOTAVAIL):errors+=1
                    else:unexpected+=1
                    break
            status=dict(identity,time=time.time(),desired=desired,held=len(held),allocation_errors=errors,unexpected_errors=unexpected)
            raw=json.dumps(status).encode();os.pwrite(sf,raw,0);os.ftruncate(sf,len(raw));time.sleep(.2)
    finally:
        for old in held:os.close(old) if a.kind=='descriptors' else old.close()
        os.close(cf);os.close(sf)
if __name__=='__main__':main()
