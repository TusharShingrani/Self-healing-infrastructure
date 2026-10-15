"""Install job monitoring while preserving existing targets and rollback files."""
import base64,json,os,shlex,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mapek.cloudstack import CloudStack
from mapek.educloud import EduCloudWorld,load_lab
ROOT=Path(__file__).resolve().parents[1]

lab=load_lab();world=EduCloudWorld(CloudStack(project=lab['project_id']),'monitor',lab,key_path=os.environ['LAB_SSH_KEY'])
vm=world._refresh()
if not vm or vm.get('projectid')!=lab['project_id'] or world.cs.ip_of(vm)!=lab['addresses']['monitor'] or not world._ssh.reachable():raise RuntimeError('Monitor identity unproven')
files={rel:base64.b64encode((ROOT/rel).read_bytes()).decode() for rel in ('monitoring/rules/healer.yml','monitoring/rules/jobs.yml','monitoring/grafana/dashboards/jobs.json','monitoring/grafana/dashboards/infrastructure.json')}
ca=json.loads((Path.home()/'.config/healer-jobs/kube.json').read_text())['ca']  # Public trust anchor only.
config=json.loads((ROOT/'config/jobs-lab.json').read_text())
code='''
import base64,json,os,shutil,subprocess,tempfile,time,yaml
from pathlib import Path
files=FILES
ca=CA
config=CONFIG
root=Path('/etc/prometheus');stamp=str(int(time.time()))
paths={
 'monitoring/rules/healer.yml':root/'rules/healer.yml',
 'monitoring/rules/jobs.yml':root/'rules/jobs.yml',
 'monitoring/grafana/dashboards/jobs.json':Path('/var/lib/grafana/dashboards/jobs.json'),
 'monitoring/grafana/dashboards/infrastructure.json':Path('/var/lib/grafana/dashboards/infrastructure.json')}
paths_before={p:p.read_bytes() if p.exists() else None for p in list(paths.values())+[root/'prometheus.yml',root/'blackbox.yml',root/'healer-k3s-ca.pem']}
backup=root/('before-jobs-'+stamp);backup.mkdir(mode=0o700)
for i,(p,data) in enumerate(paths_before.items()):
 if data is not None:(backup/(str(i)+'-'+p.name)).write_bytes(data)
prom=yaml.safe_load((root/'prometheus.yml').read_text());black=yaml.safe_load((root/'blackbox.yml').read_text())
new=[
 {'job_name':'expanded_nodes','static_configs':[{'targets':[s['address']+':9100'],'labels':{'node':n}} for n,s in config['nodes'].items()]},
 {'job_name':'jobs_healer','static_configs':[{'targets':['10.1.1.205:9109']}]},
 {'job_name':'jobs_client','static_configs':[{'targets':['10.1.1.84:9107']}]},
 {'job_name':'jobs_database','static_configs':[{'targets':['10.1.1.83:9108']}]},
]
for name,url,module in [('jobs_readiness',config['api_url']+'/readyz','http_job_ready'),('jobs_policy_witness','http://10.1.1.80:30081/status','http_job_policy'),('jobs_api_server','https://10.1.1.80:6443/readyz','http_k3s_ready')]:
 new.append({'job_name':name,'metrics_path':'/probe','params':{'module':[module]},'static_configs':[{'targets':[url]}],
  'relabel_configs':[{'source_labels':['__address__'],'target_label':'__param_target'},{'source_labels':['__param_target'],'target_label':'target'},{'target_label':'__address__','replacement':'127.0.0.1:9115'}]})
names={j['job_name'] for j in new};prom['scrape_configs']=[j for j in prom['scrape_configs'] if j['job_name'] not in names]+new
black['modules'].update({
 'http_job_ready':{'prober':'http','timeout':'5s','http':{'valid_status_codes':[200],'fail_if_body_not_matches_regexp':['"ready": *true']}},
 'http_job_policy':{'prober':'http','timeout':'5s','http':{'valid_status_codes':[200],'fail_if_body_not_matches_regexp':['"database_network_allowed": *true','"monitor_network_denied": *true']}},
 'http_k3s_ready':{'prober':'http','timeout':'5s','http':{'valid_status_codes':[200],'tls_config':{'ca_file':'/etc/prometheus/healer-k3s-ca.pem'}}}})
try:
 for relative,p in paths.items():
  p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(files[relative]));os.chmod(p,0o644)
 (root/'healer-k3s-ca.pem').write_bytes(base64.b64decode(ca));os.chmod(root/'healer-k3s-ca.pem',0o644)
 (root/'prometheus.yml').write_text(yaml.safe_dump(prom));(root/'blackbox.yml').write_text(yaml.safe_dump(black))
 subprocess.run(['promtool','check','config',str(root/'prometheus.yml')],check=True)
 subprocess.run(['systemctl','restart','prometheus-blackbox-exporter','prometheus'],check=True)
 import pwd,grp
 for p in paths.values():
  if 'grafana' in str(p):os.chown(p,pwd.getpwnam('grafana').pw_uid,grp.getgrnam('grafana').gr_gid)
 print('Existing targets preserved; job workflow, all five hosts, API server and policy witness monitored')
except Exception:
 for p,data in paths_before.items():
  if data is None:p.unlink(missing_ok=True)
  else:p.write_bytes(data)
 subprocess.run(['systemctl','restart','prometheus-blackbox-exporter','prometheus']);raise
'''.replace('files=FILES','files='+repr(files)).replace('ca=CA','ca='+repr(ca)).replace('config=CONFIG','config='+repr(config))
world._ssh.timeout=120
ok,out,err=world._probe('sudo python3 -c '+shlex.quote(code));print(out,err)
if not ok:raise RuntimeError('Job monitor update did not verify; inspect current configuration and rollback record')
