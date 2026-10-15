"""Independent client: submit, await completion and verify deterministic result."""
import hashlib,json,sqlite3,threading,time,urllib.request,urllib.error
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path('/etc/healer-jobs')
CONFIG=json.loads((ROOT/'client.json').read_text())
LATEST={'healthy':False,'error':'no completed sample','time':0};TOTAL={'ok':0,'failed':0}

def request(path,data=None):
    payload=None if data is None else json.dumps(data).encode()
    req=urllib.request.Request(CONFIG['url']+path,data=payload,headers={'Authorization':'Bearer '+CONFIG['token'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=4) as response:return json.load(response)

def sample():
    start=time.monotonic();payload='selfheal-canary-'+str(time.time_ns())
    with sqlite3.connect('/var/lib/job-probe/receipts.db') as receipts:
        receipts.execute('CREATE TABLE IF NOT EXISTS receipts(job_id INTEGER PRIMARY KEY,expected TEXT,submitted REAL,verified INTEGER DEFAULT 0)')
        for ident,expected in receipts.execute('SELECT job_id,expected FROM receipts WHERE verified=1 ORDER BY job_id DESC LIMIT 20'):
            previous=request('/jobs/'+str(ident))
            if previous['status']!='done' or previous['result']!=expected:
                return {'healthy':False,'integrity_check':False,'job_id':ident,'time':time.time(),'error':'previously acknowledged result changed'}
        accepted=request('/jobs',{'payload':payload});ident=accepted['id'];deadline=time.monotonic()+30
        receipts.execute('INSERT INTO receipts(job_id,expected,submitted) VALUES(?,?,?)',(ident,hashlib.sha256(payload.encode()).hexdigest(),time.time()));receipts.commit()
    while time.monotonic()<deadline:
        result=request('/jobs/'+str(ident))
        if result['status']=='done':
            ok=result['result']==hashlib.sha256(payload.encode()).hexdigest()
            with sqlite3.connect('/var/lib/job-probe/receipts.db') as receipts:
                receipts.execute('UPDATE receipts SET verified=? WHERE job_id=?',(int(ok),ident))
                receipts.execute('DELETE FROM receipts WHERE submitted<?',(time.time()-86400,))
            return {'healthy':ok,'integrity_check':ok,'job_id':ident,'correct_result':ok,'seconds':time.monotonic()-start,'time':time.time(),'error':'' if ok else 'incorrect result'}
        time.sleep(.5)
    return {'healthy':False,'job_id':ident,'time':time.time(),'error':'completion deadline exceeded'}

def loop():
    global LATEST
    while True:
        start=time.monotonic()
        try:result=sample()
        except (OSError,ValueError,KeyError):result={'healthy':False,'time':time.time(),'error':'API or database operation unavailable'}
        LATEST=result;TOTAL['ok' if result['healthy'] else 'failed']+=1
        print(json.dumps(result),flush=True);time.sleep(max(1,10-(time.monotonic()-start)))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        view=LATEST
        if self.path=='/metrics':
            text=f'job_client_healthy {int(view["healthy"])}\njob_client_last_sample_seconds {view["time"]}\njob_client_completion_seconds {view.get("seconds",0)}\n'
            text+=''.join(f'job_client_samples_total{{result="{k}"}} {v}\n' for k,v in TOTAL.items());body=text.encode();kind='text/plain'
        elif self.path=='/status':body=json.dumps(view).encode();kind='application/json'
        else:self.send_error(404);return
        self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass

if __name__=='__main__':
    import sys
    if sys.argv[1:]==['--once']:print(json.dumps(sample()),flush=True)
    else:threading.Thread(target=loop,daemon=True).start();ThreadingHTTPServer(('10.1.1.84',9107),Handler).serve_forever()
