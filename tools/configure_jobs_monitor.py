"""Install only monitoring for the bank statement use case; keep rollback files."""
import argparse,base64,json,os,shlex,sys,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mapek.cloudstack import CloudStack
from mapek.educloud import EduCloudWorld,load_lab
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--retire-legacy',action='store_true',help='Deprecated compatibility flag; bank-statement monitoring is always installed')
args=parser.parse_args()
for unit in ('healer-loop','healer-infrastructure'):
    if subprocess.run(['systemctl','--user','is-active','--quiet',unit]).returncode==0:
        raise RuntimeError('Stop and back up historical controllers before retiring their scrape targets')

lab=load_lab();world=EduCloudWorld(CloudStack(project=lab['project_id']),'monitor',lab,key_path=os.environ['LAB_SSH_KEY'])
vm=world._refresh()
if not vm or vm.get('projectid')!=lab['project_id'] or world.cs.ip_of(vm)!=lab['addresses']['monitor'] or not world._ssh.reachable():raise RuntimeError('Monitor identity unproven')
# The two management hosts are part of this use case's resource monitoring.
healer=world.cs.instance(lab['healer_instance'])
if not healer or healer.get('projectid')!=lab['project_id'] or world.cs.ip_of(healer)!=lab['healer_guest_ip']:
    raise RuntimeError('Healer identity unproven before enabling host monitoring')
install="test -x /usr/bin/prometheus-node-exporter || { sudo apt-get -o DPkg::Lock::Timeout=120 update -qq && sudo env DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=120 install -y -qq prometheus-node-exporter; }; sudo systemctl enable --now prometheus-node-exporter"
if subprocess.run(['bash','-c',install]).returncode:raise RuntimeError('Healer host metrics installation failed')
world._ssh.timeout=180
ok,_,err=world._probe(install)
if not ok:raise RuntimeError('Monitor host metrics installation failed: '+err[:200])
files={rel:base64.b64encode((ROOT/rel).read_bytes()).decode() for rel in ('monitoring/rules/jobs.yml','monitoring/grafana/dashboards/jobs.json','monitoring/prometheus.yml','monitoring/blackbox.yml','monitoring/grafana/provisioning/dashboards/selfheal.yml')}
bank_ca=json.loads((Path.home()/'.config/healer-jobs/client.json').read_text())['ca']
ca=json.loads((Path.home()/'.config/healer-jobs/kube.json').read_text())['ca']  # Public trust anchor only.
config=json.loads((ROOT/'config/jobs-lab.json').read_text())
code='''
import base64,json,os,shutil,subprocess,tempfile,time,yaml
from pathlib import Path
files=FILES
ca=CA
bank_ca=BANK_CA
config=CONFIG
retire_legacy=RETIRE
root=Path('/etc/prometheus');stamp=str(int(time.time()))
paths={
 'monitoring/rules/jobs.yml':root/'rules/jobs.yml',
 'monitoring/grafana/dashboards/jobs.json':Path('/var/lib/grafana/dashboards/jobs.json'),
 'monitoring/grafana/provisioning/dashboards/selfheal.yml':Path('/etc/grafana/provisioning/dashboards/selfheal.yml')}
paths_before={p:p.read_bytes() if p.exists() else None for p in list(paths.values())+[root/'prometheus.yml',root/'blackbox.yml',root/'healer-k3s-ca.pem',root/'bank-ca.pem']}
backup=root/('before-jobs-'+stamp);backup.mkdir(mode=0o700)
for i,(p,data) in enumerate(paths_before.items()):
 if data is not None:(backup/(str(i)+'-'+p.name)).write_bytes(data)
prom=yaml.safe_load(base64.b64decode(files['monitoring/prometheus.yml']));black=yaml.safe_load(base64.b64decode(files['monitoring/blackbox.yml']))
new=[
 {'job_name':'job_nodes','static_configs':[{'targets':[s['address']+':9100'],'labels':{'node':n}} for n,s in config['nodes'].items()]},
 {'job_name':'jobs_healer','static_configs':[{'targets':['10.1.1.205:9109']}]},
 {'job_name':'jobs_client','static_configs':[{'targets':['10.1.1.84:9107']}]},
 {'job_name':'jobs_database','static_configs':[{'targets':['10.1.1.83:9108']}]},
]
for name,url,module in [('jobs_readiness',config['api_url']+'/readyz','http_job_ready'),('jobs_policy_witness','http://10.1.1.80:30081/status','http_job_policy'),('jobs_api_server','https://10.1.1.80:6443/readyz','http_k3s_ready')]:
 new.append({'job_name':name,'metrics_path':'/probe','params':{'module':[module]},'static_configs':[{'targets':[url]}],
  'relabel_configs':[{'source_labels':['__address__'],'target_label':'__param_target'},{'source_labels':['__param_target'],'target_label':'target'},{'target_label':'__address__','replacement':'127.0.0.1:9115'}]})
prom['scrape_configs'] += new
black['modules'].update({
 'http_job_ready':{'prober':'http','timeout':'5s','http':{'valid_status_codes':[200],'fail_if_body_not_matches_regexp':['"ready": *true'],'tls_config':{'ca_file':'/etc/prometheus/bank-ca.pem'}}},
 'http_job_policy':{'prober':'http','timeout':'5s','http':{'valid_status_codes':[200],'fail_if_body_not_matches_regexp':['"database_network_allowed": *true','"monitor_network_denied": *true']}},
 'http_k3s_ready':{'prober':'http','timeout':'5s','http':{'valid_status_codes':[200],'tls_config':{'ca_file':'/etc/prometheus/healer-k3s-ca.pem'}}}})
try:
 # Archive only the obsolete lab dashboards/rules; preserve their bytes for rollback.
 retired={}
 for p in (root/'rules/healer.yml',Path('/var/lib/grafana/dashboards/selfheal.json'),Path('/var/lib/grafana/dashboards/infrastructure.json')):
  if p.exists():
   retired[p]=p.read_bytes();(backup/('retired-'+p.name)).write_bytes(retired[p]);p.unlink()
 home=Path('/etc/systemd/system/grafana-server.service.d/selfheal.conf')
 if home.exists():
  paths_before[home]=home.read_bytes();(backup/'grafana-service.conf').write_bytes(paths_before[home])
  home.write_text(home.read_text().replace('/var/lib/grafana/dashboards/selfheal.json','/var/lib/grafana/dashboards/jobs.json'))
 for relative,p in paths.items():
  p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(files[relative]));os.chmod(p,0o644)
 (root/'bank-ca.pem').write_bytes(base64.b64decode(bank_ca));os.chmod(root/'bank-ca.pem',0o644)
 (root/'healer-k3s-ca.pem').write_bytes(base64.b64decode(ca));os.chmod(root/'healer-k3s-ca.pem',0o644)
 (root/'prometheus.yml').write_text(yaml.safe_dump(prom));(root/'blackbox.yml').write_text(yaml.safe_dump(black))
 subprocess.run(['promtool','check','config',str(root/'prometheus.yml')],check=True)
 subprocess.run(['systemctl','daemon-reload'],check=True)
 subprocess.run(['systemctl','restart','prometheus-blackbox-exporter','prometheus','grafana-server'],check=True)
 import pwd,grp
 for p in paths.values():
  if 'grafana' in str(p):os.chown(p,pwd.getpwnam('grafana').pw_uid,grp.getgrnam('grafana').gr_gid)
 print('Only bank-statement monitoring is active; old dashboards and rules archived for rollback')
except Exception:
 for p,data in retired.items():p.write_bytes(data)
 for p,data in paths_before.items():
  if data is None:p.unlink(missing_ok=True)
  else:p.write_bytes(data)
 subprocess.run(['systemctl','daemon-reload']);subprocess.run(['systemctl','restart','prometheus-blackbox-exporter','prometheus','grafana-server']);raise
'''.replace('files=FILES','files='+repr(files)).replace('ca=CA','ca='+repr(ca)).replace('bank_ca=BANK_CA','bank_ca='+repr(bank_ca)).replace('config=CONFIG','config='+repr(config)).replace('retire_legacy=RETIRE','retire_legacy='+repr(args.retire_legacy))
world._ssh.timeout=120
ok,out,err=world._probe('sudo python3 -c '+shlex.quote(code));print(out,err)
if not ok:raise RuntimeError('Job monitor update did not verify; inspect current configuration and rollback record')
