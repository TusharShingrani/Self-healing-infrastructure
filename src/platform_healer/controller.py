"""One serial controller, durable Knowledge and a deliberately small operator UI."""
import argparse
import hmac
import json
import secrets
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .engine import Engine
from .knowledge import Knowledge
from .transport import RemoteClient
from .investigation import GeminiAdvisor, evidence_packet, require_current_evidence

from .operator_ui import PAGE


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',default='/etc/platform-healer/controller.json')
    args=parser.parse_args()
    config=json.loads(Path(args.config).read_text())
    token=Path(config['token_file']).read_text().strip()
    if len(token)<32:raise ValueError('A private operator token is required')
    targets={}
    for spec in config['targets']:
        targets[spec['id']]=dict(spec,key=Path(spec['key_file']).read_bytes(),
            client=RemoteClient(spec['url'],config.get('allow_plaintext_lab',False),spec.get('tls_directory')))
    knowledge=Knowledge(config['database']);engine=Engine(knowledge,targets)
    # An interrupted request must not remain running forever after process restart.
    knowledge.db.execute("UPDATE investigations SET status='unavailable' WHERE status='running'");knowledge.db.commit()
    investigation_gate=threading.Lock()
    def investigate(ident,actor):
        settings=config.get('investigation',{})
        if not settings.get('enabled',False):raise ValueError('Gemini investigation is disabled; configure model and secret first')
        advisor=GeminiAdvisor(settings['model'])
        if not investigation_gate.acquire(blocking=False):raise ValueError('An investigation is already running')
        try:
            with engine.lock:
                row=knowledge.db.execute('SELECT * FROM incidents WHERE id=?',(ident,)).fetchone()
                if not row or json.loads(row['before'])['target'] not in targets:raise ValueError('Not an active gateway incident')
                recent=knowledge.db.execute('SELECT MAX(updated) FROM investigations').fetchone()[0]
                if recent and time.time()-recent<60:raise ValueError('Wait 60 seconds between provider requests')
                packet=evidence_packet(dict(row),engine.observations.get(json.loads(row['before'])['target']))
                require_current_evidence(packet)
                knowledge.begin_investigation(ident,actor)
        except Exception:
            investigation_gate.release();raise
        def run():
            try:
                try:result=advisor.investigate(packet);passed=True
                except Exception:result={'error':'Provider unavailable or invalid response; investigate manually'};passed=False
                with engine.lock:knowledge.finish_investigation(ident,result,passed)
            finally:investigation_gate.release()
        threading.Thread(target=run,daemon=True).start()
    sessions={};last_tick=[0];last_error=['']
    def loop():
        while True:
            try:engine.tick();last_tick[0]=time.time();last_error[0]=''
            except Exception as exc:last_error[0]=type(exc).__name__
            time.sleep(1)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):super().setup();self.connection.settimeout(5)
        def reply(self,status,value,content_type='application/json',cookie=None):
            raw=value.encode() if isinstance(value,str) else json.dumps(value,allow_nan=False).encode()
            self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
            if cookie:self.send_header('Set-Cookie',cookie)
            self.end_headers();self.wfile.write(raw)
        def authorised(self):
            cookie=SimpleCookie()
            try:cookie.load(self.headers.get('Cookie',''))
            except Exception:return False
            session=cookie.get('platform_session')
            return bool(session and sessions.get(session.value,0)>time.time())
        def do_GET(self):
            if self.path=='/':return self.reply(200,PAGE,'text/html; charset=utf-8')
            if self.path=='/healthz':return self.reply(200 if time.time()-last_tick[0]<15 else 503,{'loop_fresh':time.time()-last_tick[0]<15,'error':last_error[0]})
            if self.path=='/metrics':
                snapshot=engine.snapshot()
                active_incidents=[c for c in snapshot['incidents'] if json.loads(c['before'])['target'] in snapshot['policies']]
                active_scopes={c['scope'] for c in active_incidents}
                active_procedures=[p for p in snapshot['procedures'] if p['scope'] in active_scopes]
                lines=[f'platform_controller_loop_fresh {int(time.time()-last_tick[0]<15)}']
                for status in ('pending','approved','executing','verified','failed'):
                    lines.append('platform_incidents{status="'+status+'"} '+str(sum(c['status']==status for c in active_incidents)))
                for status in ('candidate','validated','suspended'):
                    lines.append('platform_procedures{status="'+status+'"} '+str(sum(p['status']==status for p in active_procedures)))
                return self.reply(200,'\n'.join(lines)+'\n','text/plain; version=0.0.4')
            if not self.authorised():return self.reply(401,{'error':'Sign in with the local operator token'})
            if self.path=='/api/status':return self.reply(200,engine.snapshot())
            self.reply(404,{'error':'Unknown route'})
        def do_POST(self):
            try:
                if self.headers.get('Origin') not in config['allowed_origins']:raise ValueError('Origin refused')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4096 or self.headers.get('Transfer-Encoding'):raise ValueError('Bounded JSON required')
                data=json.loads(self.rfile.read(size))
                if self.path=='/login':
                    if not hmac.compare_digest(str(data.get('token','')),token):
                        time.sleep(.3);return self.reply(403,{'error':'Invalid token'})
                    for ident in list(sessions):
                        if sessions[ident]<time.time():del sessions[ident]
                    if len(sessions)>32:raise ValueError('Session limit reached')
                    session=secrets.token_urlsafe(32);sessions[session]=time.time()+3600
                    # Browser transport is the explicit localhost SSH tunnel.
                    # Agent mTLS policy must never control browser cookie flags.
                    return self.reply(200,{'signed_in':True},cookie='platform_session='+session+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600'+('' if config.get('operator_http_over_ssh',False) else '; Secure'))
                if not self.authorised():return self.reply(401,{'error':'Authentication required'})
                if self.path=='/api/approve':engine.approve(int(data['incident']),data['actor'],data['reason'])
                elif self.path=='/api/investigate':investigate(int(data['incident']),data['actor'])
                elif self.path=='/api/human-repair':
                    with engine.lock:
                        row=knowledge.db.execute('SELECT before FROM incidents WHERE id=?',(int(data['incident']),)).fetchone()
                        if not row or json.loads(row['before'])['target'] not in targets:raise ValueError('Not an active incident')
                        knowledge.record_human_repair(int(data['incident']),data['actor'],data['detail'],data['verification'])
                elif self.path=='/api/mode':engine.set_mode(data['target'],data['mode'],data['actor'],data['reason'])
                elif self.path=='/api/promote':engine.promote(data['scope'],data['cause'],data['action'],data['actor'])
                elif self.path=='/api/suspend':
                    if not data['actor'].strip():raise ValueError('Reviewer required')
                    with engine.lock:knowledge.suspend(data['scope'],data['cause'],data['action'],data['actor'])
                else:return self.reply(404,{'error':'Unknown route'})
                self.reply(200,{'accepted':True})
            except Exception as exc:self.reply(409,{'error':str(exc)[:160]})
        def log_message(self,*args):pass
    threading.Thread(target=loop,daemon=True).start()
    HTTPServer(('0.0.0.0',8085),Handler).serve_forever()

if __name__=='__main__':main()
