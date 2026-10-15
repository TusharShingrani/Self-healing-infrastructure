"""Read-only database health and authoritative job counts; runs as postgres."""
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import psycopg2

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            with psycopg2.connect(dbname='jobs_lab',user='postgres',connect_timeout=3) as db:
                with db.cursor() as cursor:
                    cursor.execute("SELECT count(*) FILTER(WHERE status='pending'),count(*) FILTER(WHERE status='done'),COALESCE(extract(epoch FROM now()-min(created_at) FILTER(WHERE status='pending')),0),count(*) FILTER(WHERE status='done' AND result IS NULL) FROM jobs")
                    pending,done,age,invalid=cursor.fetchone()
            data={'up':1,'pending':pending,'done':done,'oldest_pending_seconds':float(age),'invalid_results':invalid}
        except psycopg2.Error:data={'up':0}
        if self.path=='/metrics':body=''.join(f'job_database_{k} {v}\n' for k,v in data.items()).encode();kind='text/plain'
        elif self.path=='/status':body=json.dumps(data).encode();kind='application/json'
        else:self.send_error(404);return
        self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass

if __name__=='__main__':ThreadingHTTPServer(('10.1.1.83',9108),Handler).serve_forever()
