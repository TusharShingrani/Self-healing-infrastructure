"""Administrator-only monitor migration; fixed config files, validated rollback."""
import json
from pathlib import Path
from deploy_lab import Admin,ROOT


def main():
    admin=Admin(json.loads((ROOT/'config/educloud.json').read_text()))
    files={name:(ROOT/'monitoring'/name).read_text() for name in ('prometheus.json','rules.json','blackbox.json','dashboard.json')}
    ca=admin.run('k8s-control',"sudo k3s kubectl config view --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}'").decode()
    program='''
import base64,grp,json,os,pwd,shutil,subprocess,time
from pathlib import Path
files=FILES
ca=CA
root=Path('/etc/prometheus');backup=Path('/var/backups')/('platform-monitor-'+str(int(time.time())))
backup.mkdir(mode=0o700)
paths={root/'prometheus.yml':files['prometheus.json'],root/'blackbox.yml':files['blackbox.json'],
       root/'rules/platform.json':files['rules.json'],Path('/var/lib/grafana/dashboards/platform.json'):files['dashboard.json'],
       root/'healer-k3s-ca.pem':base64.b64decode(ca).decode(),
       Path('/etc/grafana/provisioning/dashboards/selfheal.yml'):PROVIDER}
old={p:p.read_bytes() if p.exists() else None for p in paths}
retire=[root/'rules/jobs.yml',root/'rules/healer.yml',Path('/var/lib/grafana/dashboards/jobs.json'),
        Path('/var/lib/grafana/dashboards/selfheal.json'),Path('/var/lib/grafana/dashboards/infrastructure.json')]
for p in retire:
    if p.exists():old[p]=p.read_bytes()
home=Path('/etc/systemd/system/grafana-server.service.d/selfheal.conf')
if home.exists():
    old[home]=home.read_bytes();paths[home]=home.read_text().replace('/var/lib/grafana/dashboards/jobs.json','/var/lib/grafana/dashboards/platform.json').replace('/var/lib/grafana/dashboards/selfheal.json','/var/lib/grafana/dashboards/platform.json')
for index,(p,data) in enumerate(old.items()):
    if data is not None:(backup/(str(index)+'-'+p.name)).write_bytes(data)
try:
    for p,data in paths.items():p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data);p.chmod(0o644)
    for p in retire:p.unlink(missing_ok=True)
    os.chown('/var/lib/grafana/dashboards/platform.json',pwd.getpwnam('grafana').pw_uid,grp.getgrnam('grafana').gr_gid)
    subprocess.run(['promtool','check','config',str(root/'prometheus.yml')],check=True)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','restart','prometheus-blackbox-exporter','prometheus','grafana-server'],check=True)
    print('Platform-only monitoring installed; rollback copy retained')
except Exception:
    for p,data in old.items():
        if data is None:p.unlink(missing_ok=True)
        else:p.write_bytes(data)
    subprocess.run(['systemctl','daemon-reload']);subprocess.run(['systemctl','restart','prometheus-blackbox-exporter','prometheus','grafana-server']);raise
'''.replace('files=FILES','files='+repr(files)).replace('ca=CA','ca='+repr(ca)).replace('PROVIDER',repr('apiVersion: 1\nproviders:\n  - name: selfheal\n    folder: Platform tuning\n    type: file\n    disableDeletion: false\n    allowUiUpdates: false\n    options:\n      path: /var/lib/grafana/dashboards\n'))
    print(admin.run('monitor','sudo python3 -',program.encode()).decode())


if __name__=='__main__':main()
