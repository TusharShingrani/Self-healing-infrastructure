"""Small deterministic job service. PostgreSQL is authoritative; no customer data."""
import hashlib
import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import psycopg2

COUNTS={'submitted':0,'completed':0,'errors':0}

def connect():
    return psycopg2.connect(host=os.environ['DB_HOST'],dbname='jobs_lab',user='jobs_app',
                            password=os.environ['DB_PASSWORD'],connect_timeout=3,
                            application_name='selfheal-job-'+os.environ.get('ROLE','api'))

def worker_once():
    with connect() as db:
        with db.cursor() as cursor:
            cursor.execute("SELECT id,payload FROM jobs WHERE status='pending' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1")
            row=cursor.fetchone()
            if not row:return False
            result=hashlib.sha256(row[1].encode()).hexdigest()
            cursor.execute("UPDATE jobs SET status='done',result=%s,completed_at=now() WHERE id=%s",(result,row[0]))
    COUNTS['completed']+=1
    return True

def worker_loop():
    while True:
        try:
            if not worker_once():time.sleep(.25)
        except (psycopg2.Error,OSError):
            COUNTS['errors']+=1;time.sleep(1)

class Handler(BaseHTTPRequestHandler):
    def respond(self,status,data):
        body=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

    def allowed(self):
        return hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+os.environ['API_TOKEN'])

    def do_GET(self):
        if self.path=='/livez':return self.respond(200,{'alive':True})
        if self.path=='/readyz':
            try:
                with connect() as db:
                    with db.cursor() as cursor:cursor.execute('SELECT 1');cursor.fetchone()
                return self.respond(200,{'ready':True})
            except (psycopg2.Error,OSError):return self.respond(503,{'ready':False,'component':'database'})
        if self.path=='/metrics':
            body=''.join(f'job_process_{name}_total {value}\n' for name,value in COUNTS.items()).encode()
            self.send_response(200);self.send_header('Content-Type','text/plain');self.end_headers();self.wfile.write(body);return
        if not self.allowed():return self.respond(401,{'error':'authentication required'})
        if self.path.startswith('/jobs/') and self.path[6:].isdigit():
            try:
                with connect() as db:
                    with db.cursor() as cursor:
                        cursor.execute('SELECT id,status,result FROM jobs WHERE id=%s',(int(self.path[6:]),));row=cursor.fetchone()
                return self.respond(200,{'id':row[0],'status':row[1],'result':row[2]}) if row else self.respond(404,{'error':'unknown job'})
            except (psycopg2.Error,OSError):return self.respond(503,{'error':'database unavailable'})
        self.respond(404,{'error':'unknown endpoint'})

    def do_POST(self):
        if self.path!='/jobs':return self.respond(404,{'error':'unknown endpoint'})
        if not self.allowed():return self.respond(401,{'error':'authentication required'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=4096:return self.respond(413,{'error':'request too large'})
            data=json.loads(self.rfile.read(size));payload=data.get('payload')
            if not isinstance(payload,str) or not 1<=len(payload.encode())<=1024:return self.respond(400,{'error':'payload must be 1..1024 UTF-8 bytes'})
            with connect() as db:
                with db.cursor() as cursor:
                    cursor.execute('INSERT INTO jobs(payload) VALUES(%s) RETURNING id',(payload,));ident=cursor.fetchone()[0]
            COUNTS['submitted']+=1;self.respond(201,{'id':ident,'status':'pending'})
        except (ValueError,TypeError,AttributeError):self.respond(400,{'error':'invalid JSON request'})
        except (psycopg2.Error,OSError):COUNTS['errors']+=1;self.respond(503,{'error':'database unavailable'})

    def log_message(self,*args):pass

if __name__=='__main__':
    if os.environ.get('ROLE')=='worker':threading.Thread(target=worker_loop,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
