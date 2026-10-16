"""Fictional bank statement API/worker. No payments or ledger mutations."""
import hmac,json,os,ssl,threading,time,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import psycopg2
from banking import request_fields,statement,digest
COUNTS={'submitted':0,'completed':0,'errors':0}

def connect():
    role='bank_worker' if os.environ.get('ROLE')=='worker' else 'bank_api'
    return psycopg2.connect(host=os.environ['DB_HOST'],dbname='jobs_lab',user=role,
        password=os.environ['DB_PASSWORD'],connect_timeout=3,sslmode='verify-full',
        sslrootcert='/app/bank-ca.crt',application_name='statement-'+role)

def worker_once():
    with connect() as db:
        with db.cursor() as c:
            c.execute("SELECT id,account_id FROM statement_requests WHERE status='pending' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1")
            row=c.fetchone()
            if not row:return False
            ident,account=row
            c.execute('SELECT opening_balance_cents FROM bank_accounts WHERE account_id=%s',(account,));opening=c.fetchone()[0]
            c.execute('SELECT entry_id,booked_on,description,amount_cents FROM bank_ledger WHERE account_id=%s ORDER BY booked_on,entry_id',(account,))
            doc=statement(account,opening,c.fetchall())
            c.execute("UPDATE statement_requests SET status='done',document=%s::jsonb,document_hash=%s,completed_at=clock_timestamp() WHERE id=%s",(json.dumps(doc),digest(doc),ident))
    COUNTS['completed']+=1;return True

def worker_loop():
    while True:
        try:
            if not worker_once():time.sleep(.25)
        except (psycopg2.Error,OSError,ValueError):COUNTS['errors']+=1;time.sleep(1)

class Handler(BaseHTTPRequestHandler):
    def respond(self,status,data):
        body=json.dumps(data).encode();self.send_response(status)
        self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

    def account(self):
        value=self.headers.get('Authorization','')
        for variable,account in [('API_TOKEN','DEMO-NL-001'),('SECOND_API_TOKEN','DEMO-NL-002')]:
            token=os.environ.get(variable)
            if token and hmac.compare_digest(value,'Bearer '+token):return account
        return None

    def do_GET(self):
        if self.path=='/livez':return self.respond(200,{'alive':True})
        if self.path=='/readyz':
            try:
                with connect() as db:
                    with db.cursor() as c:c.execute('SELECT 1 FROM bank_accounts LIMIT 1');c.fetchone()
                return self.respond(200,{'ready':True})
            except (psycopg2.Error,OSError):return self.respond(503,{'ready':False,'component':'database'})
        if self.path=='/metrics':
            body=''.join(f'job_process_{k}_total {v}\n' for k,v in COUNTS.items()).encode();self.send_response(200)
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        if self.server.server_port==8081:return self.respond(404,{'error':'monitoring endpoint only'})
        account=self.account()
        if not account:return self.respond(401,{'error':'authentication required'})
        if self.path=='/statements':
            try:
                with connect() as db:
                    with db.cursor() as c:
                        c.execute('SELECT id,status,created_at,completed_at,document_hash FROM statement_requests WHERE account_id=%s ORDER BY created_at DESC LIMIT 12',(account,))
                        rows=[{'id':r[0],'status':r[1],'created_at':str(r[2]),'completed_at':str(r[3]) if r[3] else None,'document_hash':r[4]} for r in c.fetchall()]
                return self.respond(200,{'account_id':account,'period':'2026-09','statements':rows})
            except (psycopg2.Error,OSError):return self.respond(503,{'error':'statement storage unavailable'})
        if self.path.startswith('/statements/'):
            try:ident=str(uuid.UUID(self.path.split('/')[-1]))
            except ValueError:return self.respond(404,{'error':'unknown statement'})
            try:
                with connect() as db:
                    with db.cursor() as c:
                        c.execute('SELECT id,status,document,document_hash,created_at,completed_at FROM statement_requests WHERE id=%s AND account_id=%s',(ident,account));row=c.fetchone()
                if not row:return self.respond(404,{'error':'unknown statement'})
                return self.respond(200,{'id':row[0],'status':row[1],'document':row[2],'document_hash':row[3],'created_at':str(row[4]),'completed_at':str(row[5]) if row[5] else None})
            except (psycopg2.Error,OSError):return self.respond(503,{'error':'statement storage unavailable'})
        self.respond(404,{'error':'unknown endpoint'})

    def do_POST(self):
        if self.server.server_port==8081 or os.environ.get('ROLE')!='api' or self.path!='/statements':return self.respond(404,{'error':'unknown endpoint'})
        account=self.account()
        if not account:return self.respond(401,{'error':'authentication required'})
        try:
            if self.headers.get('Transfer-Encoding') or self.headers.get_content_type()!='application/json':return self.respond(400,{'error':'JSON with Content-Length required'})
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=1024:return self.respond(413,{'error':'request too large'})
            period,key=request_fields(json.loads(self.rfile.read(size)))
            with connect() as db:
                with db.cursor() as c:
                    c.execute('INSERT INTO statement_requests(id,account_id,period,idempotency_key) VALUES(%s,%s,%s,%s) ON CONFLICT(account_id,idempotency_key) DO NOTHING RETURNING id',(str(uuid.uuid4()),account,period,key))
                    row=c.fetchone();created=row is not None
                    if not row:
                        c.execute('SELECT id FROM statement_requests WHERE account_id=%s AND idempotency_key=%s AND period=%s',(account,key,period));row=c.fetchone()
                        if not row:return self.respond(409,{'error':'idempotency conflict'})
            COUNTS['submitted']+=int(created);return self.respond(201 if created else 200,{'id':row[0],'replayed':not created})
        except (ValueError,TypeError,AttributeError):self.respond(400,{'error':'invalid statement request'})
        except (psycopg2.Error,OSError):COUNTS['errors']+=1;self.respond(503,{'error':'statement storage unavailable'})

    def log_message(self,*args):pass

if __name__=='__main__':
    threading.Thread(target=ThreadingHTTPServer(('0.0.0.0',8081),Handler).serve_forever,daemon=True).start()
    if os.environ.get('ROLE')=='worker':threading.Thread(target=worker_loop,daemon=True).start()
    server=ThreadingHTTPServer(('0.0.0.0',8080),Handler)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain('/run/statement-tls/tls.crt','/run/statement-tls/tls.key')
    server.socket=context.wrap_socket(server.socket,server_side=True);server.serve_forever()
