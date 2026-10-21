"""Build editable draw.io symbols and self-contained SVG views of the qualified lab.

Documentation only. No network calls or runtime effects. Layout coordinates use px.
Changing the diagram in draw.io does not round-trip into this generator.
"""
from pathlib import Path
import base64,html,json,xml.etree.ElementTree as ET
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/diagrams'
COL={'request':'#15803D','telemetry':'#2563EB','effect':'#C2410C','advice':'#7C3AED','admin':'#64748B','knowledge':'#0F766E'}
# Small original vector symbols, not vendor certification marks. Labels remain text.
ICONS={
 'operator':'<circle cx="40" cy="19" r="12"/><path d="M17 68v-9c0-23 46-23 46 0v9Z"/>',
 'laptop':'<rect x="10" y="12" width="60" height="42" rx="4"/><path d="M4 64h72l-6-10H10Z"/><path d="M29 62h22"/>',
 'server':'<rect x="18" y="7" width="44" height="66" rx="5"/><path d="M18 29h44M18 51h44M29 18h20M29 40h20M29 62h20"/><circle cx="54" cy="18" r="2"/><circle cx="54" cy="40" r="2"/><circle cx="54" cy="62" r="2"/>',
 'cluster':'<path d="M40 4 72 22v36L40 76 8 58V22Z"/><circle cx="40" cy="40" r="15"/><path d="M40 12v13M40 55v13M12 40h13M55 40h13M20 20l10 10M50 50l10 10M20 60l10-10M50 30l10-10"/>',
 'container':'<path d="M8 23 40 7l32 16v34L40 73 8 57Z"/><path d="m8 23 32 17 32-17M40 40v33M24 15l32 17"/>',
 'gateway':'<circle cx="40" cy="40" r="34"/><path d="M15 29h48m-10-9 10 9-10 9M65 51H17m10-9-10 9 10 9"/>',
 'broker':'<path d="M40 5 68 16v23c0 20-28 35-28 35S12 59 12 39V16Z"/><rect x="27" y="32" width="26" height="23" rx="3"/><path d="M31 32v-8a9 9 0 0 1 18 0v8"/><circle cx="40" cy="43" r="2"/>',
 'database':'<path d="M12 18v45c0 14 56 14 56 0V18"/><ellipse cx="40" cy="18" rx="28" ry="11"/><path d="M12 39c0 14 56 14 56 0M12 57c0 14 56 14 56 0"/>',
 'probe':'<rect x="5" y="9" width="55" height="42" rx="4"/><path d="M32 51v14M17 65h30M12 29h10l6-11 8 22 8-11h10"/><circle cx="61" cy="56" r="12"/><path d="m69 65 9 10"/>',
 'monitor':'<rect x="6" y="8" width="68" height="49" rx="4"/><path d="M40 57v13M23 70h34M17 44l13-17 12 10 20-19"/>',
 'cloud':'<path d="M20 59C1 59 1 31 20 30 18 6 53 2 60 26 82 23 87 59 64 59Z"/><path d="M40 32v35m-9-9 9 9 9-9"/>',
 'analyse':'<circle cx="32" cy="31" r="22"/><path d="m48 47 24 24M19 35l9-13 10 17 8-10"/>',
 'plan':'<path d="M15 9h50v63H15Z"/><path d="M26 25h27M26 40h27M26 55h17M21 9V4h38v5"/>',
 'verify':'<circle cx="40" cy="40" r="32"/><path d="m21 40 13 13 25-29"/>',
 'clock':'<circle cx="40" cy="40" r="32"/><path d="M40 17v25l17 10"/>',
 'stop':'<path d="M25 5h30l20 20v30L55 75H25L5 55V25Z"/><path d="M23 40h34"/>',
 'network':'<rect x="7" y="25" width="66" height="30" rx="4"/><path d="M17 36v8M28 36v8M39 36v8M50 36v8M61 36v8M40 9v16M40 55v16"/>'}

def icon_svg(kind,color):
 return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80"><g fill="white" stroke="'+color+'" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'+ICONS[kind]+'</g></svg>'

class Page:
 def __init__(self,id,title,subtitle,w=1560,h=1040):
  self.id,self.title,self.subtitle,self.w,self.h=id,title,subtitle,w,h;self.nodes={};self.edges=[];self.zones=[];self.notes=[]
 def node(self,id,kind,x,y,title,lines=(),color='telemetry',w=230,h=145):
  self.nodes[id]=dict(id=id,kind=kind,x=x,y=y,w=w,h=h,title=title,lines=list(lines),color=COL.get(color,color));return id
 def zone(self,x,y,w,h,title,fill='#F8FAFC'):self.zones.append(dict(x=x,y=y,w=w,h=h,title=title,fill=fill))
 def note(self,x,y,w,text):self.notes.append(dict(x=x,y=y,w=w,text=text))
 def edge(self,s,t,label,kind='telemetry',start='right',end='left',points=(),label_at=None,dashed=False,both=False):
  self.edges.append(dict(s=s,t=t,label=label,kind=kind,start=start,end=end,points=list(points),label_at=label_at,dashed=dashed,both=both))

P=[]
p=Page('solution','01  Whole solution','Read left to right: operate, decide, admit, change and independently verify.',1600,1060);P.append(p)
p.zone(360,160,300,540,'KUBERNETES / worker-1')
p.zone(760,160,280,260,'KUBERNETES / worker-2')
p.zone(1110,160,390,580,'HOST SERVICES / worker-2')
p.zone(1130,470,350,245,'Dedicated network namespace','#F0FDF4')
p.node('operator','operator',65,195,'Operator',['SSH tunnel + console session'],'admin')
p.node('controller','container',395,210,'MAPE-K controller',['Diagnosis, mode gate, fixed plan'])
p.node('knowledge','database',395,490,'Knowledge',['SQLite on 1 GiB PVC'],'knowledge')
p.node('agent','container',785,210,'Node agent',['mTLS API, non-root'])
p.node('broker','broker',1185,210,'Root broker',['Fixed operation + lease journal'],'effect')
p.node('gateway','gateway',1150,515,'HAProxy',['Namespace port range 32 to 256'],'request',w=190)
p.node('backend','server',1350,515,'Test backend',['Loopback only'],'request',w=120)
p.node('probe','probe',1185,820,'Independent probe',['Real nonce HTTP checks'],'request')
p.node('monitor','monitor',395,820,'Prometheus + Grafana',['Metrics and historical trends'],'telemetry')
p.node('advisor','cloud',65,490,'Optional Gemini',['Advice only, no execution'],'advice')
p.edge('operator','controller','Review / approve','admin')
p.edge('controller','agent','mTLS GET sample / HMAC POST','telemetry')
p.edge('agent','broker','Unix requests / forwarded intent','telemetry')
p.edge('broker','gateway','Bounded namespace change','effect',start='bottom',end='top',points=[(1300,440),(1245,440)],label_at=(1300,425))
p.edge('gateway','backend','HTTP','request')
p.edge('probe','gateway','HTTP :18080','request',start='top',end='bottom',points=[(1300,770),(1245,770)],label_at=(1360,780))
p.edge('broker','probe','Pull observer /status over mTLS','telemetry',start='right',end='right',points=[(1540,282),(1540,892)],label_at=(1360,760))
p.edge('controller','knowledge','Read + persist outcomes','knowledge',start='bottom',end='top')
p.edge('controller','advisor','Numeric evidence only','advice',start='left',end='top',points=[(290,282),(290,445),(180,445)],label_at=(175,410),dashed=True)
p.edge('advisor','knowledge','Advice retained for UI','advice',dashed=True)
p.edge('monitor','agent','Scrape agent via NodePort','telemetry',start='right',end='bottom',points=[(705,892),(705,450),(900,450)],label_at=(800,465),dashed=True)
p.edge('monitor','probe','Scrape observer metrics','telemetry',dashed=True)
p.note(65,830,250,'Kubernetes hosts the healer.\nHAProxy and the root broker\nare native VM host services.')
p.note(65,960,1400,'Concept view: endpoints and tunnel hops are on page 02. Arrows show the request initiator; responses use the same channel. Advice never authorises an effect.')

p=Page('network','02  Network and deployment','Private EduCloud lab. Addresses are lab inventory, not a universal deployment template.',1700,1160);P.append(p)
p.zone(330,180,1050,930,'EDUCLOUD LAB / management subnet 10.1.1.0/24')
p.node('laptop','laptop',40,210,'Laptop',['OpenVPN + local browser'],'admin',w=220)
p.node('vpn','cloud',40,480,'SSH forwarding IP',['10.53.14.225:22'],'admin',w=220)
p.node('bastion','server',380,220,'healer-ubuntu',['10.1.1.205','SSH administration + tunnels'],'admin')
p.node('control','cluster',785,220,'k8s-control',['10.1.1.80 / K3s server','NodePort 30885 / 30919'])
p.node('worker1','server',1170,220,'k8s-worker-1',['10.1.1.81','Controller Pod :8085 + PVC'])
p.node('monitor','monitor',380,600,'monitor',['10.1.1.50','Grafana :3000 / Prometheus :9090'])
p.node('worker2','server',785,600,'k8s-worker-2',['10.1.1.82','Agent :9119 / broker / gateway'])
p.node('probe','probe',1170,600,'probe-1',['10.1.1.84','mTLS observer :9106 + client'])
p.node('ns','gateway',785,975,'worker-2 namespace',['10.203.0.2:18080','Backend 127.0.0.1:19080'],'request')
p.node('gemini','cloud',1430,220,'Gemini API',['HTTPS :443','Opt-in egress only'],'advice',w=190)
p.edge('laptop','vpn','Reach over OpenVPN','admin',start='bottom',end='top')
p.edge('vpn','bastion','Forward SSH to .205:22','admin',start='right',end='left',points=[(300,552),(300,292)])
p.edge('bastion','control','SSH local forward to :30885','admin')
p.edge('control','worker1','Service forwards to Pod :8085','admin')
p.edge('worker1','gemini','Allowlisted evidence','advice',dashed=True)
p.edge('worker1','worker2','In-cluster mTLS service :9119','telemetry',start='bottom',end='top',points=[(1285,450),(900,450)],label_at=(1275,465))
p.edge('worker2','probe','Broker pulls /status :9106','telemetry')
p.edge('probe','ns','Route /32 via .82; HTTP :18080','request',start='bottom',end='right',points=[(1285,1047)],label_at=(1290,975))
p.edge('worker2','ns','veth .1 / .2, 10.203.0.0/30','request',start='bottom',end='top')
p.edge('monitor','control','Scrape :30885 / :30919','telemetry',start='top',end='bottom',points=[(495,480),(900,480)],label_at=(635,465),dashed=True)
p.edge('monitor','probe','Scrape observer :9106','telemetry',start='bottom',end='bottom',points=[(495,870),(1285,870)],label_at=(650,855),dashed=True)
p.note(40,800,235,'Laptop forwards:\n127.0.0.1:8085 to console\nlocalhost:3000 to Grafana\nlocalhost:9090 to Prometheus')
p.note(40,1000,650,'Admin SSH from bastion reaches all five other VMs.\nNode exporters :9100 on all six VMs; these repeated links are omitted.')
p.note(1110,1000,490,'No namespace default route. Only probe .84 may reach\nthe private frontend. Return: .84/32 via 10.203.0.1.')

p=Page('mapek','03  MAPE-K and safety','Controller stages describe an implemented decision loop, not an animated progress bar.',1600,1210);P.append(p)
p.zone(60,160,1450,650,'CONTROLLER / platform-healer namespace')
p.node('monitor','probe',110,205,'MONITOR',['Fresh same-identity sample','Agent pulls broker evidence'])
p.node('analyse','analyse',510,205,'ANALYSE',['Correlate repeated failures','Healthy backend + errno 99'])
p.node('plan','plan',910,205,'PLAN',['Fixed range 32 to 256','Identity, expected value, lease'])
p.node('gate','broker',1260,205,'MODE GATE',['Watch / named approval /','qualified scoped reuse'],'effect',w=220)
p.node('execute','container',1260,525,'EXECUTE',['Persist HMAC operation','Send once, reconcile by ID'],'effect',w=220)
p.node('verify','verify',730,525,'VERIFY',['Three distinct client successes','At least 2 s, deadline 20 s'])
p.node('knowledge','database',310,525,'KNOWLEDGE',['Incidents, outcomes, decisions','Candidate / validated / suspended'],'knowledge',w=275)
p.node('broker','broker',1230,900,'Root admission + lease',['Fresh safety recheck','Journal before mutation'],'effect',w=270)
p.node('target','gateway',760,900,'Managed gateway',['Namespace-only sysctl','Useful requests + same identity'],'request',w=270)
p.node('investigate','operator',95,900,'Operator investigation',['Unknown / backend / unsafe','Optional advisory Gemini'],'advice',w=280)
p.edge('monitor','analyse','Fresh evidence','telemetry')
p.edge('analyse','plan','Two consecutive diagnoses','telemetry')
p.edge('plan','gate','Eligible fixed proposal','effect')
p.edge('gate','execute','Authorised; root still rechecks','effect',start='bottom',end='top')
p.edge('execute','verify','Observe actual recovery','telemetry',start='left',end='right')
p.edge('verify','knowledge','Verified or failed outcome','knowledge',start='left',end='right')
p.edge('knowledge','monitor','Next tick + scoped history','knowledge',start='top',end='bottom',points=[(447,450),(225,450)],label_at=(335,435),dashed=True)
p.edge('knowledge','gate','Two verified after last failure + named promotion','knowledge',start='top',end='bottom',points=[(447,410),(1370,410)],label_at=(965,395),dashed=True)
p.edge('execute','broker','HMAC intent via agent','effect',start='bottom',end='top')
p.edge('broker','target','Apply / safe compare-and-set rollback','effect',start='left',end='right')
p.edge('target','verify','Fresh client + gateway checks','telemetry',start='top',end='bottom',points=[(895,830),(845,830)],label_at=(1000,810),dashed=True)
p.edge('analyse','investigate','Other cause: no automatic action','advice',start='bottom',end='top',points=[(625,465),(45,465),(45,855),(235,855)],label_at=(265,840),dashed=True)
p.note(1120,710,350,'Watch only: no new dispatch.\nApproval records permission, not a direct write.')
p.note(70,1110,1450,'Failure suspends automatic reuse. A new gateway identity requires qualification again. Broker lease reconciliation runs independently of the controller and defers unsafe rollback instead of forcing it.')

p=Page('incident','04  What actually breaks, and what is repaired','Illustrative readings explain the implemented rule. They are not a new measured trial. Follow the numbered arrows.',1500,1630);P.append(p)
p.node('load','probe',90,190,'1  Make real requests',['probe-1 -> HAProxy :18080 -> backend :19080','Held connections occupy outgoing source ports.','Baseline namespace range: 40000-40031 (32 ports).'],'request',w=560,h=220)
p.node('failure','gateway',840,190,'2  New requests fail',['Example: used_ports=32, range_size=32.','Backend connect errors and HTTP 5xx rise.','Allocation probe returns errno 99: no local address.'],'request',w=560,h=220)
p.node('diagnosis','analyse',840,540,'3  Rule identifies the cause',['Port use >=85%; both transaction checks fail.','Upstream healthy; memory safe; no reserved overlap.','Two consecutive eligible diagnoses are required.'],w=560,h=220)
p.node('approval','operator',90,540,'4  Operator authorises this repair',['Console: approve expand_port_range with a reason.','Watch mode does not execute. Automatic mode needs','a matching, explicitly promoted procedure.'],'admin',w=560,h=220)
p.node('change','broker',90,890,'5  Change one Linux setting',['Root broker checks identity and expected old value.','In namespace only: ip_local_port_range becomes','40000-40255 (256 ports), with a 30-second lease.'],'effect',w=560,h=220)
p.node('success','verify',840,890,'6  Prove requests work again',['Controller checks the new range and probe results.','Require 3 distinct successes spanning >=2 seconds,','within 20 seconds. A kernel write alone is not success.'],w=560,h=220)
p.node('learn','database',840,1240,'7  Remember the verified procedure',['Store incident, exact scope, action and outcome.','After 2 verified occurrences since the last failure,','a named operator may promote reuse for that scope.'],'knowledge',w=560,h=220)
p.node('rollback','clock',90,1240,'8  Safely return to baseline',['Broker watchdog runs even if controller stops.','After lease expiry AND zero active connections,','restore 40000-40031 only if identity/value match.'],'effect',w=560,h=220)
p.edge('load','failure','HTTP workload','request')
p.edge('failure','diagnosis','Measurements via broker + agent','telemetry',start='bottom',end='top')
p.edge('diagnosis','approval','Cause: outgoing port exhaustion','telemetry',start='left',end='right')
p.edge('approval','change','Later tick sends authenticated fixed intent','effect',start='bottom',end='top')
p.edge('change','success','Readback + fresh HTTP checks','telemetry')
p.edge('success','learn','Pass records success; failure suspends reuse','knowledge',start='bottom',end='top')
p.edge('change','rollback','Separate watchdog, not a controller stage','effect',start='bottom',end='top')
p.note(70,1510,1350,'Only the namespace port pool is repaired: no HAProxy restart, VM resize, backend repair or host-wide sysctl change.\nIf the backend is down or evidence is missing, this action is refused. Gemini may explain evidence but cannot invent or run repairs.')

def anchor(n,side):
 return {'left':(n['x'],n['y']+n['h']/2),'right':(n['x']+n['w'],n['y']+n['h']/2),'top':(n['x']+n['w']/2,n['y']),'bottom':(n['x']+n['w']/2,n['y']+n['h'])}[side]

def pts(page,e):return [anchor(page.nodes[e['s']],e['start']),*e['points'],anchor(page.nodes[e['t']],e['end'])]

def label_pos(page,e):
 if e['label_at']:return e['label_at']
 points=pts(page,e);a,b=points[len(points)//2-1:len(points)//2+1]
 return ((a[0]+b[0])/2,(a[1]+b[1])/2-12)

def cell(root,id,value='',style='',parent='1',vertex=True,**attrs):
 c=ET.SubElement(root,'mxCell',dict(id=id,value=value,style=style,parent=parent,**({'vertex':'1'} if vertex else {'edge':'1'}),**attrs));return c

def geo(c,x,y,w,h):ET.SubElement(c,'mxGeometry',{'x':str(x),'y':str(y),'width':str(w),'height':str(h),'as':'geometry'})

def textcell(root,id,text,x,y,w,h,size=16,color='#334155',bold=False):
 c=cell(root,id,html.escape(text).replace('\n','<br>'),'text;html=1;whiteSpace=wrap;align=left;verticalAlign=middle;fontFamily=Helvetica;fontSize='+str(size)+';fontColor='+color+';fontStyle='+('1' if bold else '0')+';');geo(c,x,y,w,h)

def build_drawio():
 doc=ET.Element('mxfile',{'host':'app.diagrams.net','agent':'HAProxy design documentation','version':'24.7.17','type':'device'})
 for page in P:
  d=ET.SubElement(doc,'diagram',{'id':page.id,'name':page.title});m=ET.SubElement(d,'mxGraphModel',{'dx':'1600','dy':'1000','grid':'1','gridSize':'10','guides':'1','tooltips':'1','connect':'1','arrows':'1','fold':'1','page':'1','pageScale':'1','pageWidth':str(page.w),'pageHeight':str(page.h),'math':'0','shadow':'0'});r=ET.SubElement(m,'root');ET.SubElement(r,'mxCell',{'id':'0'});ET.SubElement(r,'mxCell',{'id':'1','parent':'0'})
  textcell(r,'title',page.title,40,24,page.w-80,48,28,'#0F172A',True);textcell(r,'subtitle',page.subtitle,40,75,page.w-80,40,16)
  textcell(r,'legend','GREEN: HTTP workload   BLUE: telemetry requests   ORANGE: admitted effects   PURPLE: advice / investigation   GREY: administration',40,120,page.w-80,25,13)
  for i,z in enumerate(page.zones):
   c=cell(r,'zone'+str(i),'',f"rounded=1;arcSize=8;fillColor={z['fill']};strokeColor=#CBD5E1;dashed=1;container=0;");geo(c,z['x'],z['y'],z['w'],z['h']);textcell(r,'zone-title'+str(i),z['title'],z['x']+15,z['y']+5,z['w']-30,32,14,'#475569',True)
  for i,e in enumerate(page.edges):
   color=COL[e['kind']];source=page.nodes[e['s']];target=page.nodes[e['t']];pos={'left':(0,.5),'right':(1,.5),'top':(.5,0),'bottom':(.5,1)};sx,sy=pos[e['start']];tx,ty=pos[e['end']]
   style=f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;endFill=1;strokeColor={color};strokeWidth=2;exitX={sx};exitY={sy};entryX={tx};entryY={ty};exitPerimeter=0;entryPerimeter=0;"+('dashed=1;' if e['dashed'] else '')+('startArrow=block;startFill=1;' if e['both'] else '')
   c=cell(r,'edge'+str(i),'',style,vertex=False,source=e['s'],target=e['t']);g=ET.SubElement(c,'mxGeometry',{'relative':'1','as':'geometry'})
   if e['points']:
    a=ET.SubElement(g,'Array',{'as':'points'})
    for x,y in e['points']:ET.SubElement(a,'mxPoint',{'x':str(x),'y':str(y)})
   x,y=label_pos(page,e);textcell(r,'edge-label'+str(i),e['label'],x-140,y-15,280,30,13,color)
  for n in page.nodes.values():
   group=cell(r,n['id'],'','group;');geo(group,n['x'],n['y'],n['w'],n['h'])
   image='data:image/svg+xml,'+quote(icon_svg(n['kind'],n['color']),safe='')
   c=cell(r,n['id']+'-symbol','','shape=image;imageAspect=1;aspect=fixed;image='+image+';',parent=n['id']);geo(c,n['w']/2-36,0,72,72)
   c=cell(r,n['id']+'-label',html.escape(n['title'])+'<br><font style="font-size:14px;color:#475569">'+'<br>'.join(html.escape(t) for t in n['lines'])+'</font>','text;html=1;whiteSpace=wrap;align=center;verticalAlign=top;fontSize=17;fontStyle=1;fontFamily=Helvetica;',parent=n['id']);geo(c,0,80,n['w'],n['h']-80)
  for i,n in enumerate(page.notes):textcell(r,'note'+str(i),n['text'],n['x'],n['y'],n['w'],70,14)
 ET.indent(doc,space='  ');(OUT/'haproxy-system-design.drawio').write_bytes(ET.tostring(doc,encoding='utf-8',xml_declaration=True))

def svg_text(text,x,y,size=16,color='#334155',anchor='start',weight='normal'):
 lines=text.split('\n');return '<text x="'+str(x)+'" y="'+str(y)+'" font-family="Arial,Helvetica,sans-serif" font-size="'+str(size)+'" font-weight="'+weight+'" fill="'+color+'" text-anchor="'+anchor+'">'+''.join('<tspan x="'+str(x)+'" dy="'+('0' if i==0 else str(size*1.4))+'">'+html.escape(t)+'</tspan>' for i,t in enumerate(lines))+'</text>'

def build_svgs():
 for page in P:
  a=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{page.w}" height="{page.h}" viewBox="0 0 {page.w} {page.h}" role="img" aria-labelledby="title desc"><title id="title">{html.escape(page.title)}</title><desc id="desc">{html.escape(page.subtitle)}</desc><rect width="100%" height="100%" fill="white"/><defs>']
  for k,c in COL.items():a.append(f'<marker id="arrow-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="{c}"/></marker>')
  a+=['</defs>',svg_text(page.title,40,55,28,'#0F172A',weight='bold'),svg_text(page.subtitle,40,95),svg_text('GREEN: HTTP workload    BLUE: telemetry requests    ORANGE: admitted effects    PURPLE: advice / investigation    GREY: administration',40,137,13)]
  for z in page.zones:
   a.append(f'<rect x="{z["x"]}" y="{z["y"]}" width="{z["w"]}" height="{z["h"]}" rx="12" fill="{z["fill"]}" stroke="#CBD5E1" stroke-dasharray="6 4"/>');a.append(svg_text(z['title'],z['x']+15,z['y']+25,14,'#475569',weight='bold'))
  for e in page.edges:
   points=pts(page,e);d='M '+' L '.join(f'{x},{y}' for x,y in points);color=COL[e['kind']]
   a.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" marker-end="url(#arrow-{e["kind"]})"'+(f' marker-start="url(#arrow-{e["kind"]})"' if e['both'] else '')+(' stroke-dasharray="7 5"' if e['dashed'] else '')+'/>')
   x,y=label_pos(page,e);width=min(len(e['label'])*7.2+14,405);a.append(f'<rect x="{x-width/2}" y="{y-16}" width="{width}" height="23" rx="4" fill="white" fill-opacity=".96"/>');a.append(svg_text(e['label'],x,y,13,color,anchor='middle'))
  for n in page.nodes.values():
   a.append(f'<svg x="{n["x"]+n["w"]/2-36}" y="{n["y"]}" width="72" height="72" viewBox="0 0 80 80">'+icon_svg(n['kind'],n['color']).split('>',1)[1].rsplit('</svg>',1)[0]+'</svg>')
   a.append(svg_text(n['title'],n['x']+n['w']/2,n['y']+100,17,'#0F172A','middle','bold'))
   a.append(svg_text('\n'.join(n['lines']),n['x']+n['w']/2,n['y']+124,14,'#475569','middle'))
  for n in page.notes:a.append(svg_text(n['text'],n['x'],n['y']+20,14))
  a.append('</svg>');(OUT/(page.id+'.svg')).write_text('\n'.join(a),encoding='utf-8',newline='\n')

def validate():
 for p in P:
  for e in p.edges:assert e['s'] in p.nodes and e['t'] in p.nodes
  for n in p.nodes.values():assert n['x']>=0 and n['y']>=0 and n['x']+n['w']<=p.w and n['y']+n['h']<=p.h
 doc=ET.parse(OUT/'haproxy-system-design.drawio')
 for diagram in doc.findall('diagram'):
  ids=[c.attrib['id'] for c in diagram.findall('.//mxCell')];assert len(ids)==len(set(ids))
  for c in diagram.findall('.//mxCell[@edge="1"]'):assert c.attrib['source'] in ids and c.attrib['target'] in ids
 for name in ('solution','network','mapek','incident'):ET.parse(OUT/(name+'.svg'))
 print('Validated four pages, connected edges, editable labels, inline vector symbols and SVG XML.')

if __name__=='__main__':OUT.mkdir(exist_ok=True);build_drawio();build_svgs();validate()
