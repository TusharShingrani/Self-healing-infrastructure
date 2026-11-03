"""Loopback-only service-check page; fresh requests originate on probe-1.

No operator token, approval endpoint, arbitrary URL or mutation is exposed.
The read-only monitor certificate is used only by this server, never the page.
"""
import argparse,json,ssl,threading,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from .transport import fixed_opener

OBSERVER='https://10.1.1.84:9106/check'
TARGET='http://10.203.0.2:18080'
PAGE=r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Gateway connection test</title>
<style>body{font:17px/1.5 system-ui,sans-serif;background:#edf3f8;color:#15283b;margin:0}main{max-width:860px;margin:48px auto;padding:24px}small{color:#4b6278}h1{font-size:34px;margin:8px 0}section{background:white;border:1px solid #c4d1de;border-radius:12px;padding:24px;margin:20px 0}button{background:#164d82;color:white;border:0;border-radius:6px;padding:12px 20px;font:inherit;cursor:pointer}button:disabled{opacity:.5}label{margin-left:16px}#state{font-size:30px;margin:8px 0}.ok{color:#14613d}.bad{color:#a12626}.unknown{color:#7b5200}.facts{display:flex;gap:32px;flex-wrap:wrap}.facts b{display:block}table{border-collapse:collapse;width:100%;font-size:15px}th,td{text-align:left;padding:9px;border-bottom:1px solid #dce5ed}#message{min-height:28px}a{color:#164d82}input{width:18px;height:18px}footer{font-size:14px;color:#4b6278}</style>
<main><small>FICTIONAL BANK SCENARIO / INFRASTRUCTURE RESEARCH LAB</small><h1>Can the service answer?</h1><p>A connection test through the HAProxy gateway. No payments or customer data.</p>
<section><button id="check">Check service</button><label><input type="checkbox" id="auto" checked> Check every 2 seconds</label><h2 id="state" class="unknown" role="status" aria-live="polite">Waiting for a real request</h2><p id="message">The page stays open separately when gateway requests fail.</p><div class="facts"><div>HTTP response<b id="http">—</b></div><div>Request time<b id="latency">—</b></div><div>Last checked<b id="when">—</b></div></div></section>
<section><h2>Recent requests</h2><p><small>Each row is a fresh request from the independent probe through the gateway. A successful response must also contain the expected random value.</small></p><table><thead><tr><th>Time</th><th>Result</th><th>HTTP</th><th>Duration</th></tr></thead><tbody id="history"></tbody></table></section>
<footer>This page has no repair controls. <a href="http://localhost:8085/" target="_blank" rel="noopener">Open healer console</a> · <a href="http://localhost:3000/d/platform-mapek" target="_blank" rel="noopener">Open monitoring</a><p>“Cannot check” means the observation path is unavailable; it does not establish that the gateway failed.</p></footer></main>
<script>let busy=false;const $=id=>document.getElementById(id);async function check(){if(busy)return;busy=true;$('check').disabled=true;let data;try{const r=await fetch('/api/check',{cache:'no-store'});data=await r.json();if(!r.ok)throw Error('Independent probe is unavailable');const good=data.success===true;$('state').textContent=good?'Service responding':'Service request failed';$('state').className=good?'ok':'bad';$('message').textContent=good?'The request passed through the gateway and returned the expected response.':data.status?'The gateway path returned an HTTP error or an unexpected response.':'The request could not connect or timed out.';$('http').textContent=data.status||'No HTTP response';$('latency').textContent=Math.round(data.latency_seconds*1000)+' ms';$('when').textContent=new Date(data.time*1000).toLocaleTimeString();row(data,good?'Passed':'Failed')}catch(e){$('state').textContent='Cannot check';$('state').className='unknown';$('message').textContent='The independent probe is unavailable. Investigate monitoring access; do not assume the service is healthy or failed.';$('http').textContent='Unknown';$('latency').textContent='Unknown';$('when').textContent=new Date().toLocaleTimeString();row(null,'Unknown')}finally{busy=false;$('check').disabled=false}}function row(d,result){const tr=document.createElement('tr');for(const value of [new Date((d?d.time*1000:Date.now())).toLocaleTimeString(),result,d?(d.status||'No response'):'Unknown',d?Math.round(d.latency_seconds*1000)+' ms':'Unknown']){const td=document.createElement('td');td.textContent=value;tr.append(td)}$('history').prepend(tr);while($('history').children.length>12)$('history').lastChild.remove()}$('check').onclick=check;setInterval(()=>{if($('auto').checked)check()},2000);check();</script></html>'''

def validate_result(value,now=None):
    now=time.time() if now is None else now
    if not isinstance(value,dict) or value.get('target')!=TARGET:raise ValueError('Unexpected observation target')
    if type(value.get('success')) is not bool or type(value.get('status')) is not int or not 0<=value['status']<=599:raise ValueError('Invalid request outcome')
    if type(value.get('time')) not in (int,float) or not -2<=now-value['time']<=5:raise ValueError('Stale observation')
    latency=value.get('latency_seconds')
    if type(latency) not in (int,float) or not 0<=latency<=5:raise ValueError('Invalid request duration')
    if value['success'] and value['status']!=200:raise ValueError('Inconsistent success')
    return {k:value[k] for k in ('time','success','status','latency_seconds')}

class Probe:
    def __init__(self,pki):
        context=ssl.create_default_context(cafile=str(pki/'ca.crt'))
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(pki/'monitor.crt'),str(pki/'monitor.key'))
        self.opener=fixed_opener(context)
    def check(self):
        with self.opener.open(OBSERVER,timeout=3) as response:raw=response.read(4097)
        if len(raw)>4096:raise ValueError('Oversized observation')
        return validate_result(json.loads(raw))

def make_server(probe,port=8086):
    gate=threading.BoundedSemaphore(2)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):super().setup();self.connection.settimeout(5)
        def reply(self,status,value,kind='application/json'):
            body=value if isinstance(value,bytes) else json.dumps(value).encode()
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'");self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_GET(self):
            from urllib.parse import urlsplit
            try:
                host=urlsplit('http://'+self.headers.get('Host',''))
                if host.hostname not in ('localhost','127.0.0.1','::1') or host.port!=self.server.server_port:raise ValueError('Host refused')
            except ValueError:self.reply(403,{'error':'Loopback host required'});return
            if self.path=='/':self.reply(200,PAGE.encode(),'text/html; charset=utf-8');return
            if self.path!='/api/check':self.reply(404,{'error':'Unknown path'});return
            if not gate.acquire(blocking=False):self.reply(429,{'error':'Check already running'});return
            try:self.reply(200,probe.check())
            except Exception:self.reply(502,{'error':'Independent probe unavailable'})
            finally:gate.release()
        def log_message(self,*args):pass
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pki',type=Path,default=Path.home()/'.config/platform-healer/pki');args=parser.parse_args()
    make_server(Probe(args.pki)).serve_forever()

if __name__=='__main__':main()
