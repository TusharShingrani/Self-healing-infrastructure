"""Update only the existing Grafana dashboard; retain monitoring and alert rules."""
import json
from deploy_lab import Admin, ROOT


def main():
    admin=Admin(json.loads((ROOT/'config/educloud.json').read_text()))
    dashboard=json.loads((ROOT/'monitoring/dashboard.json').read_text())
    if dashboard.get('uid')!='platform-mapek' or len(dashboard['panels'])!=4:
        raise ValueError('Unexpected gateway dashboard')
    program='''import grp,json,os,pwd,time
from pathlib import Path
dashboard=DATA
path=Path('/var/lib/grafana/dashboards/platform.json')
backup=Path('/var/backups')/('gateway-dashboard-'+str(int(time.time()))+'.json')
backup.write_bytes(path.read_bytes());backup.chmod(0o600)
temporary=path.with_suffix('.json.tmp')
temporary.write_text(json.dumps(dashboard,indent=2)+'\\n');temporary.chmod(0o644)
os.chown(temporary,pwd.getpwnam('grafana').pw_uid,grp.getgrnam('grafana').gr_gid)
temporary.replace(path)
print('Gateway dashboard updated atomically; monitoring and alert configuration unchanged.')
'''.replace('dashboard=DATA','dashboard='+repr(dashboard))
    print(admin.run('monitor','sudo python3 -',program.encode()).decode())


if __name__=='__main__':main()
