"""Linux adapters accept only root-provisioned fixture identities in this release."""
import hashlib,json,os,stat,subprocess,sys,time
from pathlib import Path
from ..model import Sample,digest

def root_json(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022:raise ValueError('Registry is not a root-owned write-protected regular file')
        return json.loads(os.read(fd,16384))
    finally:os.close(fd)

def process_pin(registry):
    pid=registry['pid']
    if type(pid)is not int or pid<=1:raise ValueError('Unsafe target PID')
    text=Path(f'/proc/{pid}/stat').read_text();start=text.rsplit(')',1)[1].split()[19]
    if start!=registry['start_time'] or os.stat(f'/proc/{pid}').st_uid!=0:raise ValueError('Process replacement or owner mismatch')
    command=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
    if b'platform_healer.fixtures' not in command:raise ValueError('Process is not the owned infrastructure fixture')
    return pid

class Fixture:
    def __init__(self,spec):
        self.spec=spec;self.target=spec['id'];self.kind=spec['kind'];self.registry=Path('/run/platform-healer/fixtures')/self.kind/'identity.json';self.status=self.registry.with_name('status.json')
        if self.target not in ('ports-canary','descriptors-canary'):raise ValueError('Unreviewed fixture target')
    def state(self):
        registry=root_json(self.registry);pid=process_pin(registry)
        if self.kind=='ports' and registry.get('namespace_inode')!=self.spec['namespace_inode']:
            raise ValueError('Fixture is outside the approved network namespace')
        latest=None
        for _ in range(3):
            try:latest=root_json(self.status);break
            except (ValueError,json.JSONDecodeError):time.sleep(.01)
        if latest is None or latest.get('pid')!=pid or latest.get('start_time')!=registry['start_time']:raise ValueError('Fixture telemetry identity mismatch')
        boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        identity=digest({'policy':self.spec,'boot':boot,'registry':registry,'plugin':1})
        return registry,latest,identity

class Ports(Fixture):
    action='expand_port_range'
    def helper(self,op,*extra):
        args=[sys.executable,'-m','platform_healer.host_helper',op,'--namespace',self.spec['namespace'],'--inode',str(self.spec['namespace_inode']),*extra]
        result=subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=4)
        if result.returncode:raise RuntimeError('Isolated namespace operation refused: '+result.stderr[-180:])
        return json.loads(result.stdout)
    def sample(self):
        registry,status,identity=self.state();m=self.helper('sample')
        m.update({'allocation_errors':status['allocation_errors'],'successful_connections':m['active_connections'],'desired_connections':status['desired']})
        return Sample(self.target,'ports',identity,status['time'],m)
    def value(self):return self.helper('sample')['range']
    def validate(self,value):
        if value not in (self.spec['baseline'],self.spec['expanded']):raise ValueError('Range is not an approved bound')
        if any(type(v)is not int for v in value) or not 40000<=value[0]<value[1]<=41023:raise ValueError('Invalid range')
        return value
    def apply(self,value):
        self.validate(value);self.state();self.helper('range','--low',str(value[0]),'--high',str(value[1]))
    def rollback_ready(self,value):return self.sample().metrics['active_connections']==0
    def verify(self):
        m=self.sample().metrics
        return m['desired_connections']>0 and m['active_connections']>=m['desired_connections'] and self.helper('verify').get('fresh_connection_echo') is True

class Descriptors(Fixture):
    action='raise_nofile_soft'
    def sample(self):
        import resource
        registry,status,identity=self.state();pid=registry['pid'];soft,hard=resource.prlimit(pid,resource.RLIMIT_NOFILE)
        m={'open_fds':len(list(Path(f'/proc/{pid}/fd').iterdir())),'soft_limit':soft,'hard_limit':hard,'allocation_errors':status['allocation_errors'],'held_fds':status['held'],'desired_fds':status['desired']}
        return Sample(self.target,'descriptors',identity,status['time'],m)
    def value(self):return self.sample().metrics['soft_limit']
    def validate(self,value):
        if type(value)is not int or value not in (self.spec['baseline'],self.spec['expanded']):raise ValueError('Unapproved descriptor ceiling')
        m=self.sample().metrics
        if m['hard_limit']!=self.spec['hard_ceiling'] or value>m['hard_limit']:raise ValueError('Hard limit changed or insufficient')
        return value
    def apply(self,value):
        import resource
        self.validate(value);registry,_,_=self.state();pid=registry['pid'];_,hard=resource.prlimit(pid,resource.RLIMIT_NOFILE);resource.prlimit(pid,resource.RLIMIT_NOFILE,(value,hard))
    def rollback_ready(self,value):
        m=self.sample().metrics;return m['held_fds']==0 and m['open_fds']<value
    def verify(self):
        m=self.sample().metrics
        return m['desired_fds']>0 and m['held_fds']>=m['desired_fds'] and m['open_fds']>=m['desired_fds'] and m['soft_limit']==self.spec['expanded']
