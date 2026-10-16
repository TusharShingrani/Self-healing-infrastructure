"""Independent statement verifier: pinned oracle, durable receipts, fresh requests."""
import base64,hashlib,json,sqlite3,ssl,threading,time,urllib.request,urllib.error,uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path('/etc/healer-jobs')
CONFIG=json.loads((ROOT/'client.json').read_text())
SSL=ssl.create_default_context(cadata=base64.b64decode(CONFIG['ca']).decode())
ORACLE_FILE=Path('/opt/healer-jobs/bank-oracle.json')
ORACLE_SHA='09a63ff8e8949ac8dac25d91bed4cce47e35219547fe0925753de872229b7880'
LATEST={'healthy':False,'error':'no completed sample','time':0};TOTAL={'ok':0,'failed':0}

def request(path,data=None):
    req=urllib.request.Request(CONFIG['url']+path,data=None if data is None else json.dumps(data).encode(),headers={'Authorization':'Bearer '+CONFIG['token'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,context=SSL,timeout=4) as response:return json.load(response)

def sample():
    raw=ORACLE_FILE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ORACLE_SHA:return {'healthy':False,'integrity_check':False,'time':time.time(),'error':'approved oracle changed'}
    oracle=json.loads(raw);expected=hashlib.sha256(json.dumps(oracle,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    with sqlite3.connect('/var/lib/job-probe/statement-receipts.db') as receipts:
        receipts.execute('CREATE TABLE IF NOT EXISTS receipts(request_id TEXT PRIMARY KEY,expected TEXT,submitted REAL,verified INTEGER DEFAULT 0)')
        for ident,previous_hash in receipts.execute('SELECT request_id,expected FROM receipts WHERE verified=1 ORDER BY submitted DESC LIMIT 20'):
            previous=request('/statements/'+ident)
            if previous['status']!='done' or previous['document_hash']!=previous_hash or previous['document']!=oracle:
                return {'healthy':False,'integrity_check':False,'time':time.time(),'error':'previously acknowledged statement changed or missing'}
        start=time.monotonic();key=str(uuid.uuid4());data={'period':'2026-09','idempotency_key':key}
        accepted=request('/statements',data);ident=accepted['id']
        if request('/statements',data)['id']!=ident:return {'healthy':False,'integrity_check':False,'time':time.time(),'error':'idempotency violation'}
        receipts.execute('INSERT INTO receipts VALUES(?,?,?,0)',(ident,expected,time.time()));receipts.commit()
    while time.monotonic()-start<30:
        result=request('/statements/'+ident)
        if result['status']=='done':
            # Literal approved ledger document, not just a server-generated hash.
            ok=result.get('document')==oracle and result.get('document_hash')==expected
            with sqlite3.connect('/var/lib/job-probe/statement-receipts.db') as receipts:receipts.execute('UPDATE receipts SET verified=? WHERE request_id=?',(int(ok),ident))
            return {'healthy':ok,'integrity_check':ok,'correct_result':ok,'idempotency_check':True,'job_id':ident,'seconds':time.monotonic()-start,'time':time.time(),'error':'' if ok else 'statement entries or balances differ from approved oracle'}
        time.sleep(.5)
    return {'healthy':False,'integrity_check':True,'job_id':ident,'time':time.time(),'error':'statement completion deadline exceeded'}

def loop():
    global LATEST
    while True:
        start=time.monotonic()
        try:result=sample()
        except (OSError,ValueError,KeyError):result={'healthy':False,'time':time.time(),'error':'statement API or database unavailable'}
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
