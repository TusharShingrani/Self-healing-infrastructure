"""Fixed namespace operations. No caller-provided commands or destinations."""
import argparse,ctypes,errno,json,os,re,socket
from pathlib import Path

def enter(name,expected):
    if not re.fullmatch(r'platform-healer-[a-z0-9-]{1,40}',name):raise ValueError('Namespace outside dedicated lab prefix')
    fd=os.open('/run/netns/'+name,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        if st.st_uid!=0 or st.st_ino!=expected or st.st_ino==os.stat('/proc/self/ns/net').st_ino:raise ValueError('Namespace identity or isolation unproven')
        libc=ctypes.CDLL(None,use_errno=True)
        if libc.setns(fd,0x40000000)!=0:raise OSError(ctypes.get_errno(),'Cannot enter approved namespace')
    finally:os.close(fd)

def read_ports(port):
    bounds=[int(v) for v in Path('/proc/sys/net/ipv4/ip_local_port_range').read_text().split()]
    reserved=Path('/proc/sys/net/ipv4/ip_local_reserved_ports').read_text().strip();used=set();active=0;wait=0
    for name in ('tcp','tcp6'):
        for line in Path('/proc/net/'+name).read_text().splitlines()[1:]:
            fields=line.split();local=int(fields[1].split(':')[1],16);remote=int(fields[2].split(':')[1],16)
            if remote!=port:continue
            if bounds[0]<=local<=bounds[1]:used.add(local)
            if fields[3]=='01':active+=1
            if fields[3]=='06':wait+=1
    return {'range':bounds,'range_size':bounds[1]-bounds[0]+1,'reserved':reserved,'used_ports':len(used),'active_connections':active,'time_wait':wait}

def main():
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['sample','range','verify']);p.add_argument('--namespace',required=True);p.add_argument('--inode',type=int,required=True);p.add_argument('--port',type=int,default=19080);p.add_argument('--low',type=int);p.add_argument('--high',type=int);a=p.parse_args()
    if a.port!=19080:raise ValueError('Only the fixed canary infrastructure endpoint is permitted')
    enter(a.namespace,a.inode)
    if a.operation=='range':
        if type(a.low)is not int or type(a.high)is not int or not 40000<=a.low<a.high<=41023:raise ValueError('Outside canary port bounds')
        reserved=read_ports(a.port)['reserved']
        for piece in filter(None,reserved.split(',')):
            values=[int(v) for v in piece.split('-')];low=values[0];high=values[-1]
            if max(low,a.low)<=min(high,a.high):raise ValueError('Requested range overlaps reserved ports')
        Path('/proc/sys/net/ipv4/ip_local_port_range').write_text(f'{a.low} {a.high}\n')
    if a.operation=='verify':
        with socket.create_connection(('127.0.0.1',a.port),timeout=2) as s:
            value=os.urandom(16);s.sendall(value);data=b''
            while len(data)<len(value):
                part=s.recv(len(value)-len(data))
                if not part:break
                data+=part
            print(json.dumps({'fresh_connection_echo':data==value}));return
    print(json.dumps(read_ports(a.port)))
if __name__=='__main__':main()
