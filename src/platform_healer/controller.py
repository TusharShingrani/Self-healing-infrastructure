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

PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Platform healer</title><style>body{font:16px system-ui;max-width:1050px;margin:40px auto;padding:20px;background:#f4f6f8;color:#17273b}section{background:white;padding:20px;margin:16px 0;border-radius:10px}button,input{font:inherit;padding:9px;margin:5px}pre{white-space:pre-wrap;overflow-wrap:anywhere}small{color:#43566d}</style>
<h1>Kernel & platform healer</h1><p>Patient: Linux infrastructure resources on the isolated canary worker.</p>
<section id="login"><label>Operator access token <input id="token" type="password" autocomplete="current-password"></label><button id="sign">Sign in</button></section>
<p id="message" role="status"></p><main id="content" hidden>
<section><h2>How this works</h2><p>Monitor actual resource pressure â†’ analyse correlated allocation failures â†’ plan a bounded repair â†’ approve and execute â†’ verify useful work â†’ record Knowledge.</p><p>First occurrences need approval. Two verified occurrences allow an operator to promote a procedure for automatic reuse within the same scope. No arbitrary AI commands, node restarts or cloud deletion.</p></section>
<section><h2>Live observations</h2><div id="observations"></div></section>
<section><h2>Incidents and operator decisions</h2><div id="incidents"></div></section>
<section><h2>Learned procedures</h2><div id="procedures"></div></section>
<section><h2>Execution and verification</h2><pre id="executions"></pre></section>
<section><h2>Audit trail</h2><pre id="audit"></pre></section></main>
<script>
const msg=document.getElementById('message');
async function api(path,data){let r=await fetch(path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});let v=await r.json();if(!r.ok)throw Error(v.error||'Request refused');return v}
function text(parent,tag,value){let e=document.createElement(tag);e.textContent=value;parent.append(e);return e}
async function decision(path,data){try{await api(path,data);await refresh()}catch(e){msg.textContent=e.message}}
document.getElementById('sign').onclick=async()=>{try{await api('/login',{token:document.getElementById('token').value});document.getElementById('token').value='';await refresh()}catch(e){msg.textContent=e.message}};
async function refresh(){try{let s=await api('/api/status');document.getElementById('login').hidden=true;document.getElementById('content').hidden=false;msg.textContent='Updated '+new Date().toLocaleTimeString();let o=document.getElementById('observations');o.replaceChildren();for(let [target,v] of Object.entries(s.observations)){text(o,'h3',target+' â€” '+v.cause);text(o,'p',v.detail);text(o,'pre',JSON.stringify(v.sample?.metrics||{},null,2))}let i=document.getElementById('incidents');i.replaceChildren();for(let c of [...s.incidents].reverse()){let a=text(i,'section','');text(a,'h3','#'+c.id+' '+c.cause+' â€” '+c.status);text(a,'p','Proposed action: '+(c.action||'Investigation required; no executable repair'));if(c.status==='pending'&&c.action){let actor=document.createElement('input');actor.placeholder='Reviewer name';let reason=document.createElement('input');reason.placeholder='Why is this repair appropriate?';a.append(actor,reason);let b=text(a,'button','Approve bounded repair');b.onclick=()=>decision('/api/approve',{incident:c.id,actor:actor.value,reason:reason.value})}}let p=document.getElementById('procedures');p.replaceChildren();for(let c of s.procedures){let a=text(p,'section','');text(a,'p',c.cause+' â†’ '+c.action+' â€” '+c.status);if(c.status==='validated'){let actor=document.createElement('input');actor.placeholder='Reviewer name';a.append(actor);let b=text(a,'button','Suspend automatic reuse');b.onclick=()=>decision('/api/suspend',{scope:c.scope,cause:c.cause,action:c.action,actor:actor.value})}if(c.status!=='validated'){let actor=document.createElement('input');actor.placeholder='Reviewer name';a.append(actor);let b=text(a,'button','Promote after two verified occurrences');b.onclick=()=>decision('/api/promote',{scope:c.scope,cause:c.cause,action:c.action,actor:actor.value})}}document.getElementById('executions').textContent=JSON.stringify(s.executions,null,2);document.getElementById('audit').textContent=JSON.stringify(s.audit.slice(-20),null,2)}catch(e){msg.textContent=e.message}}
refresh();setInterval(refresh,3000);
</script></html>'''


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
            client=RemoteClient(spec['url'],config.get('allow_plaintext_lab',False)))
    knowledge=Knowledge(config['database']);engine=Engine(knowledge,targets)
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
                lines=[f'platform_controller_loop_fresh {int(time.time()-last_tick[0]<15)}']
                for status in ('pending','approved','executing','verified','failed'):
                    lines.append('platform_incidents{status="'+status+'"} '+str(sum(c['status']==status for c in snapshot['incidents'])))
                for status in ('candidate','validated','suspended'):
                    lines.append('platform_procedures{status="'+status+'"} '+str(sum(p['status']==status for p in snapshot['procedures'])))
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
                    return self.reply(200,{'signed_in':True},cookie='platform_session='+session+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600'+('' if config.get('allow_plaintext_lab') else '; Secure'))
                if not self.authorised():return self.reply(401,{'error':'Authentication required'})
                if self.path=='/api/approve':engine.approve(int(data['incident']),data['actor'],data['reason'])
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
