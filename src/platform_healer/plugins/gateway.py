"""Fixed HAProxy namespace integration. No PID-based resource mutation."""
import csv
import errno
import hashlib
import io
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from .linux import root_json
from ..model import Sample,digest
from ..tls import client_context
from ..transport import fixed_opener

ROOT=Path('/run/platform-healer/gateway')
REGISTRY=Path('/run/platform-healer/gateway-identity.json')


def unix_request(path,request,limit=65536):
    with socket.socket(socket.AF_UNIX) as stream:
        stream.settimeout(.8);stream.connect(str(path));stream.sendall(request)
        raw=b''
        while True:
            part=stream.recv(min(4096,limit+1-len(raw)))
            if not part:break
            raw+=part
            if len(raw)>limit:raise ValueError('Gateway response exceeds bound')
        return raw


def transaction(path):
    nonce=secrets.token_hex(12)
    request=('GET /transaction?nonce='+nonce+' HTTP/1.0\r\nConnection: close\r\n\r\n').encode()
    try:
        response=unix_request(path,request,8192);headers,body=response.split(b'\r\n\r\n',1)
        return headers.splitlines()[0].split()[1]==b'200' and body==('gateway-ok:'+nonce+'\n').encode()
    except (OSError,ValueError,IndexError):return False


def reserved_overlap(text,bounds):
    for item in filter(None,text.split(',')):
        parts=[int(v) for v in item.split('-')]
        if max(parts[0],bounds[0])<=min(parts[-1],bounds[1]):return True
    return False


def admission(metrics,spec):
    if metrics.get('upstream_healthy') is not True:raise ValueError('Upstream unavailable: port tuning is not an eligible repair')
    if metrics.get('memory_available_bytes',0)<spec['minimum_memory_bytes'] or metrics.get('memory_available_ratio',0)<spec['minimum_memory_ratio']:
        raise ValueError('Insufficient measured host memory headroom')
    if metrics.get('reserved_conflict') is not False:raise ValueError('Approved expansion conflicts with reserved ports')
    if metrics.get('active_connections',10**9)>128:raise ValueError('Connection count exceeds qualified load bound')


class Gateway:
    action='expand_port_range'
    def __init__(self,spec):
        if spec['id']!='gateway-ports' or spec['namespace']!='platform-healer-gateway':raise ValueError('Unreviewed gateway target')
        self.spec=spec;self.target=spec['id'];self.kind='gateway_ports'
        self.cooldown_seconds=spec.get('cooldown_seconds',30)
        self.context=client_context('/etc/platform-healer/tls')
        self.observer=fixed_opener(self.context)
    def state(self):
        registry=root_json(REGISTRY);pid=registry['pid']
        if type(pid)is not int or pid<=1:raise ValueError('Unsafe gateway PID')
        start=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
        if start!=registry['start_time'] or os.stat(f'/proc/{pid}').st_uid!=self.spec['uid']:raise ValueError('Gateway process identity changed')
        if os.stat(f'/proc/{pid}/ns/net').st_ino!=self.spec['namespace_inode']:raise ValueError('Gateway namespace changed')
        if str(Path(f'/proc/{pid}/exe').resolve())!='/usr/sbin/haproxy':raise ValueError('Gateway executable replaced')
        if '/system.slice/platform-gateway.service' not in Path(f'/proc/{pid}/cgroup').read_text():raise ValueError('Gateway unit ownership changed')
        for path,expected in (('/usr/sbin/haproxy',self.spec['executable_sha256']),('/etc/platform-gateway/gateway.cfg',self.spec['config_sha256'])):
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=expected:raise ValueError('Gateway executable/configuration fingerprint changed')
        identity=digest({'policy':self.spec,'registry':registry,'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'plugin':1})
        return identity
    def helper(self,operation,*extra):
        result=subprocess.run([sys.executable,'-m','platform_healer.host_helper',operation,'--namespace',self.spec['namespace'],'--inode',str(self.spec['namespace_inode']),*extra],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=3)
        if result.returncode:raise ValueError('Pinned gateway namespace operation refused')
        return json.loads(result.stdout)
    def sample(self):
        identity=self.state();metrics=self.helper('sample')
        raw=unix_request(ROOT/'haproxy.sock',b'show stat\n').decode()
        rows=list(csv.DictReader(io.StringIO(raw.lstrip('# '))))
        backend=next(row for row in rows if row['pxname']=='upstream' and row['svname']=='BACKEND')
        metrics.update(backend_connect_errors=int(backend['econ']),gateway_5xx=int(backend['hrsp_5xx']),gateway_sessions=int(backend['scur']))
        memory={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:','MemAvailable:'))}
        metrics.update(memory_available_bytes=memory['MemAvailable'],memory_available_ratio=memory['MemAvailable']/memory['MemTotal'])
        metrics['upstream_healthy']=transaction(ROOT/'upstream.sock')
        metrics['gateway_transaction_ok']=transaction(ROOT/'frontend.sock')
        metrics['allocation_probe_errno']=self.helper('allocate')['errno'] if metrics['used_ports']/metrics['range_size']>=.8 else 0
        metrics['reserved_conflict']=reserved_overlap(metrics['reserved'],self.spec['expanded'])
        metrics['headroom_safe']=metrics['memory_available_bytes']>=self.spec['minimum_memory_bytes'] and metrics['memory_available_ratio']>=self.spec['minimum_memory_ratio']
        error=''
        try:
            with self.observer.open('https://10.1.1.84:9106/status',timeout=.7) as response:observer=json.loads(response.read(4097))
            if observer.get('target')!='http://10.203.0.2:18080' or type(observer.get('success')) is not bool or not -2<=time.time()-observer['time']<=5:raise ValueError('Independent observer stale or mismatched')
            metrics['client_transaction_ok']=observer['success'];metrics['independent_probe_time']=observer['time']
        except (OSError,ValueError,KeyError,TypeError) as exc:
            metrics['client_transaction_ok']=False;metrics['independent_probe_time']=0;error='Independent client telemetry unavailable or stale'
        return Sample(self.target,self.kind,identity,time.time(),metrics,error=error)
    def value(self):return self.helper('sample')['range']
    def validate(self,value):
        if value not in (self.spec['baseline'],self.spec['expanded']) or any(type(v)is not int for v in value):raise ValueError('Unapproved gateway port range')
        if value==self.spec['expanded']:
            sample=self.sample()
            if not sample.valid():raise ValueError('Fresh independent gateway evidence required')
            admission(sample.metrics,self.spec)
        return value
    def apply(self,value):
        self.validate(value);self.state();self.helper('range','--low',str(value[0]),'--high',str(value[1]))
    def rollback_ready(self,value):return self.sample().metrics['active_connections']==0
    def verify(self):
        sample=self.sample()
        return sample.valid() and sample.metrics['upstream_healthy'] and sample.metrics['gateway_transaction_ok'] and sample.metrics['client_transaction_ok']
