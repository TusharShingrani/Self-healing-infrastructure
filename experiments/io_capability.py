"""Bounded storage-priority comparison on the isolated benchmark VM only.

Never touches K3s/etcd/SQLite platform files. A positive comparison is exploratory
evidence, not permission to enable a production scheduling mutation.
"""
import json,mmap,multiprocessing,os,random,shutil,socket,statistics,subprocess,tempfile,time
from pathlib import Path


def compete(path,stop):
    fd=os.open(path,os.O_RDWR|os.O_DIRECT)
    buffer=mmap.mmap(-1,65536)
    try:
        while not stop.is_set():
            start=time.monotonic()
            os.pwrite(fd,buffer,random.randrange(2048)*65536)
            # At most roughly 10 MiB/s; bounded duration and owned file only.
            time.sleep(max(0,.00625-(time.monotonic()-start)))
    finally:buffer.close();os.close(fd)


def measure(path,seconds=4):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT,0o600);latencies=[]
    deadline=time.monotonic()+seconds
    try:
        while time.monotonic()<deadline:
            start=time.monotonic();os.pwrite(fd,b'x'*4096,0);os.fsync(fd)
            latencies.append(time.monotonic()-start);time.sleep(.02)
    finally:os.close(fd)
    ordered=sorted(latencies)
    return {'operations':len(ordered),'p50_seconds':statistics.median(ordered),'p95_seconds':ordered[int(.95*(len(ordered)-1))]}


def main():
    if socket.gethostname()!='probe-1' or os.geteuid()!=0:raise RuntimeError('Only the dedicated owned benchmark VM is permitted')
    if shutil.disk_usage('/var/tmp').free<1024**3:raise RuntimeError('Insufficient safety headroom')
    scheduler=Path('/sys/block/vda/queue/scheduler').read_text().strip()
    evidence={'scheduler':scheduler,'time':time.time(),'pairs':[],'target':'owned temporary benchmark files','automatic_io_repair_enabled':False}
    if '[mq-deadline]' not in scheduler and '[bfq]' not in scheduler:
        evidence['result']='unsupported scheduler';print(json.dumps(evidence));return
    with tempfile.TemporaryDirectory(prefix='platform-healer-io-',dir='/var/tmp') as root:
        contender=str(Path(root)/'competitor.bin');critical=str(Path(root)/'durability.bin')
        with open(contender,'wb') as f:f.truncate(128*1024**2)
        stop=multiprocessing.Event();process=multiprocessing.Process(target=compete,args=(contender,stop));process.start()
        try:
            for occurrence in range(3):
                pair={'occurrence':occurrence+1}
                for label,priority in (('best_effort',['-c','2','-n','4']),('idle',['-c','3'])):
                    if not process.is_alive():raise RuntimeError('Competitor failed; comparison invalid')
                    subprocess.run(['ionice',*priority,'-p',str(process.pid)],check=True,capture_output=True)
                    pair[label]=measure(critical)
                evidence['pairs'].append(pair)
        finally:
            stop.set();process.join(3)
            if process.is_alive():process.terminate();process.join(3)
    ratios=[p['idle']['p95_seconds']/p['best_effort']['p95_seconds'] for p in evidence['pairs']]
    evidence['idle_to_best_effort_p95_ratios']=ratios
    evidence['result']='exploratory benefit; not qualified for automation' if all(v<.8 for v in ratios) else 'no consistent measured benefit; automatic action unsupported'
    print(json.dumps(evidence,indent=2))

if __name__=='__main__':main()
