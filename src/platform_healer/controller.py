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
<h1>HAProxy gateway healer</h1><p><a href="http://localhost:3000/d/platform-mapek?from=now-15m&amp;to=now">Open the platform monitoring dashboard</a></p><p>Managed service: the HAProxy HTTP gateway on worker-2. A separate client on probe-1 checks real requests through the gateway. We repair outgoing-port capacity while keeping the gateway process running.</p>
<section id="login"><label>Operator access token <input id="token" type="password" autocomplete="current-password"></label><button id="sign">Sign in</button><p>Or select your private local token file: <label>Operator token file <input id="tokenfile" type="file" accept=".token,text/plain"></label></p></section>
<p id="message" role="status"></p><main id="content" hidden>
<section><h2>How this works</h2><p>Monitor actual resource pressure &rarr; analyse correlated allocation failures &rarr; plan a bounded repair &rarr; approve and execute &rarr; verify useful work &rarr; record Knowledge.</p><p>First occurrences need approval. Two verified occurrences allow an operator to promote a procedure for automatic reuse within the same scope. No arbitrary AI commands, node restarts or cloud deletion.</p></section>
<section><h2>Operating mode</h2><p>Modes affect new actions; existing leases still reconcile safely. Automatic mode only reuses explicitly qualified procedures.</p><div id="modes"></div></section><section><h2>Live observations</h2><div id="observations"></div></section>
<section><h2>Incidents and operator decisions</h2><div id="incidents"></div></section>
<section><h2>Learned procedures</h2><div id="procedures"></div></section>
<section><h2>Execution and verification</h2><pre id="executions"></pre></section>
<section><h2>Audit trail (includes archived regression history)</h2><pre id="audit"></pre></section></main>
<script>
const msg=document.getElementById('message');
const drafts={};
const names={gateway_ports:'HAProxy outbound connection capacity',gateway_outbound_port_exhaustion:'Gateway outgoing ports exhausted',gateway_dependency_unavailable:'Upstream unavailable - investigate dependency',gateway_unsafe_headroom:'Tuning refused: low memory headroom',gateway_reserved_port_conflict:'Tuning refused: reserved-port conflict',gateway_investigation_required:'Client transaction failed - investigate',ports:'Outbound connection capacity',descriptors:'Process file-descriptor capacity',healthy:'Healthy',unknown:'Needs investigation',outbound_port_exhaustion:'Outgoing connections cannot obtain a local port',process_descriptor_exhaustion:'The process cannot open more files or sockets'};
const metrics={client_transaction_ok:'Independent client transaction succeeds',gateway_transaction_ok:'Gateway local transaction succeeds',upstream_healthy:'Upstream independently healthy',backend_connect_errors:'HAProxy backend connection errors (cumulative)',gateway_5xx:'HAProxy HTTP 5xx responses (cumulative)',allocation_probe_errno:'Namespace allocation probe errno (99 = no local port available)',memory_available_ratio:'Host memory available fraction',reserved_conflict:'Expansion conflicts with reserved ports',open_fds:'Open descriptors',soft_limit:'Current soft ceiling',hard_limit:'Fixed hard ceiling',held_fds:'Successful test allocations',desired_fds:'Required allocations',active_connections:'Established outgoing connections',desired_connections:'Required connections',range_size:'Available port numbers in the range',used_ports:'Occupied local port numbers',allocation_errors:'Allocation failures since fixture start (cumulative)',time_wait:'Sockets in TIME_WAIT'};
async function api(path,data){const r=await fetch(path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});const value=await r.json();if(r.status===401){document.getElementById('login').hidden=false;document.getElementById('content').hidden=true}if(!r.ok)throw Error(value.error||'Request refused');return value}
function text(parent,tag,value){const e=document.createElement(tag);e.textContent=value;parent.append(e);return e}
function input(parent,label,key){const wrapper=text(parent,'label',label+' ');const e=document.createElement('input');e.placeholder=label;e.value=drafts[key]||'';e.oninput=()=>{drafts[key]=e.value};wrapper.append(e);return e}
async function decision(path,data){try{await api(path,data);await refresh()}catch(error){msg.textContent=error.message}}
async function signIn(token){try{await api('/login',{token:token});document.getElementById('token').value='';await refresh()}catch(error){msg.textContent=error.message}}
document.getElementById('sign').onclick=()=>signIn(document.getElementById('token').value);
document.getElementById('tokenfile').onchange=async(event)=>{const file=event.target.files[0];if(!file)return;if(file.size>512){msg.textContent='Select only the small operator token file';event.target.value='';return}const token=(await file.text()).trim();event.target.value='';await signIn(token)};
function observations(snapshot){
  const parent=document.getElementById('observations');parent.replaceChildren();
  for(const [target,value] of Object.entries(snapshot.observations)){
    const card=text(parent,'section','');const sample=value.sample;
    text(card,'h3',(names[sample?.kind]||target)+' - '+(names[value.cause]||value.cause));
    text(card,'p','Target: '+target+' on '+(snapshot.policies[target]?.node||'the canary'));
    text(card,'p',value.detail);
    for(const [name,label] of Object.entries(metrics))if(sample?.metrics[name]!==undefined)text(card,'p',label+': '+sample.metrics[name]);
    text(card,'small','A cumulative error count can remain non-zero after recovery. The diagnosis uses new failures between fresh observations.');
  }
}
function incidents(snapshot){
  const parent=document.getElementById('incidents');parent.replaceChildren();
  const current=snapshot.incidents.filter(item=>snapshot.policies[JSON.parse(item.before).target]);
  if(!current.length)text(parent,'p','No incident recorded for the managed gateway. The controller is observing.');
  for(const item of [...current].reverse()){
    const card=text(parent,'section','');const before=JSON.parse(item.before);const policy=snapshot.policies[before.target];
    text(card,'h3','#'+item.id+' - '+(names[item.cause]||item.cause)+' - '+item.status);
    text(card,'p','Target: '+before.target+' on '+(policy?.node||'the configured canary'));
    if(item.action&&policy)text(card,'p','Reviewed proposal: '+item.action+'; baseline '+JSON.stringify(policy.baseline)+' to '+JSON.stringify(policy.expanded)+'. Temporary lease; no process restart.');
    else text(card,'p','Investigation-only record. No executable repair is attached to this evidence.');
    const evidence=text(card,'details','');text(evidence,'summary','Inspect exact before / after evidence');
    text(evidence,'pre',JSON.stringify({before:before,after:item.after?JSON.parse(item.after):null},null,2));
    if(item.status==='pending'&&item.action&&policy?.mode==='observe')text(card,'p','Observe-only mode blocks repairs. Change operating mode before approving.');
    if(item.status==='pending'&&item.action&&policy?.mode!=='observe'){const actor=input(card,'Reviewer name','incident-'+item.id+'-actor');const reason=input(card,'Why is this repair appropriate?','incident-'+item.id+'-reason');const button=text(card,'button','Approve this bounded repair');button.onclick=()=>decision('/api/approve',{incident:item.id,actor:actor.value,reason:reason.value})}
  }
}
function procedures(snapshot){
  const parent=document.getElementById('procedures');parent.replaceChildren();
  const scopes=new Set(snapshot.incidents.filter(item=>snapshot.policies[JSON.parse(item.before).target]).map(item=>item.scope));
  const current=snapshot.procedures.filter(item=>scopes.has(item.scope));
  if(!current.length)text(parent,'p','Nothing is qualified for automatic gateway reuse yet.');
  for(const item of current){
    const card=text(parent,'section','');text(card,'h3',(names[item.cause]||item.cause)+' - '+item.status);
    text(card,'p','Procedure: '+item.action+'. Exact identity/policy scope: '+item.scope.slice(0,16));
    text(card,'p',item.status==='validated'?'Automatic reuse is permitted only for a matching scoped incident.':'Automatic reuse is not permitted. Promotion requires two distinct verified occurrences.');
    const actor=input(card,'Procedure reviewer','procedure-'+item.scope+'-actor');const active=item.status==='validated';
    const button=text(card,'button',active?'Suspend automatic reuse':'Promote qualified procedure');
    button.onclick=()=>decision(active?'/api/suspend':'/api/promote',{scope:item.scope,cause:item.cause,action:item.action,actor:actor.value});
  }
}
function modes(snapshot){
  const parent=document.getElementById('modes');parent.replaceChildren();
  for(const [target,policy] of Object.entries(snapshot.policies)){
    const card=text(parent,'section','');text(card,'h3',target+' - '+policy.mode);
    const actor=input(card,'Mode operator','mode-'+target+'-actor');const reason=input(card,'Reason for mode change','mode-'+target+'-reason');
    for(const [mode,label] of [['observe','Observe only'],['reviewed','Require approval'],['automatic','Use validated procedures']]){
      const button=text(card,'button',label);button.disabled=policy.mode===mode;
      button.onclick=()=>decision('/api/mode',{target:target,mode:mode,actor:actor.value,reason:reason.value});
    }
  }
}
async function refresh(){
  try{const snapshot=await api('/api/status');document.getElementById('login').hidden=true;document.getElementById('content').hidden=false;
    msg.textContent='Updated '+new Date().toLocaleTimeString();observations(snapshot);if(!document.activeElement?.closest('#incidents,#procedures,#modes')){incidents(snapshot);procedures(snapshot);modes(snapshot)}
    const currentIds=new Set(snapshot.incidents.filter(item=>snapshot.policies[JSON.parse(item.before).target]).map(item=>item.id));
    document.getElementById('executions').textContent=JSON.stringify(snapshot.executions.filter(item=>currentIds.has(item.incident)),null,2);
    document.getElementById('audit').textContent=JSON.stringify(snapshot.audit.slice(-20),null,2);
  }catch(error){msg.textContent=error.message}
}
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
            client=RemoteClient(spec['url'],config.get('allow_plaintext_lab',False),spec.get('tls_directory')))
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
