#!/usr/bin/env python3
"""Append lab monitoring jobs, preserving current monitor configuration."""
import base64
import json
import os
import shlex
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mapek.educloud import EduCloudWorld,load_lab
from mapek.cloudstack import CloudStack


def main():
    lab=load_lab();node=EduCloudWorld(CloudStack(project=lab['project_id']),'monitor',lab,key_path=os.environ.get('LAB_SSH_KEY'))
    vm=node._refresh()
    if not vm or vm.get('projectid')!=lab['project_id'] or node.cs.ip_of(vm)!=lab['addresses']['monitor'] or not node._ssh.reachable():
        raise RuntimeError('Monitor ownership, address or pinned transport unproven')
    root=Path(__file__).resolve().parents[1]
    payload={name:base64.b64encode(root.joinpath(name).read_bytes()).decode() for name in
             ('monitoring/prometheus.yml','monitoring/blackbox.yml','monitoring/grafana/dashboards/infrastructure.json')}
    code='''
import base64,json,shutil,subprocess,time,yaml
from pathlib import Path
files=PAYLOAD
incoming={k:base64.b64decode(v).decode() for k,v in files.items()}
p=Path('/etc/prometheus/prometheus.yml');b=Path('/etc/prometheus/blackbox.yml')
stamp=str(int(time.time()))
oldp=p.read_text();oldb=b.read_text()
shutil.copy2(p,str(p)+'.before-infrastructure-'+stamp)
shutil.copy2(b,str(b)+'.before-infrastructure-'+stamp)
current=yaml.safe_load(oldp);new=yaml.safe_load(incoming['monitoring/prometheus.yml'])
names={j['job_name'] for j in current['scrape_configs']}
current['scrape_configs'] += [j for j in new['scrape_configs'] if j['job_name'] in ('infrastructure','infrastructure_transaction') and j['job_name'] not in names]
black=yaml.safe_load(oldb);black['modules']['http_infrastructure']=yaml.safe_load(incoming['monitoring/blackbox.yml'])['modules']['http_infrastructure']
try:
 p.write_text(yaml.safe_dump(current));b.write_text(yaml.safe_dump(black))
 subprocess.run(['promtool','check','config',str(p)],check=True)
 subprocess.run(['systemctl','restart','prometheus-blackbox-exporter','prometheus'],check=True)
 d=Path('/var/lib/grafana/dashboards/infrastructure.json');d.write_text(incoming['monitoring/grafana/dashboards/infrastructure.json'])
 import pwd,grp
 import os
 os.chown(d,pwd.getpwnam('grafana').pw_uid,grp.getgrnam('grafana').gr_gid);os.chmod(d,0o644)
 print('Monitor jobs appended; existing jobs preserved; dashboard provisioned')
except Exception:
 p.write_text(oldp);b.write_text(oldb);subprocess.run(['systemctl','restart','prometheus-blackbox-exporter','prometheus']);raise
'''.replace('PAYLOAD',repr(payload))
    ok,out,err=node._probe('sudo python3 -c '+shlex.quote(code))
    print(out,err)
    if not ok:raise RuntimeError('Monitor configuration failed and was rolled back')


if __name__=='__main__':main()
