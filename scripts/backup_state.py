"""Create private consistent recovery files on the management host.

Copy the resulting directory off-platform. Never publish its contents.
"""
import json,shlex,time
from pathlib import Path
from deploy_lab import Admin,ROOT


def main():
    admin=Admin(json.loads((ROOT/'config/educloud.json').read_text()))
    destination=Path.home()/'.local/state/platform-healer/backups'/str(int(time.time()))
    destination.mkdir(mode=0o700,parents=True)
    program='''
import io,sqlite3,sys,tarfile,tempfile
from pathlib import Path
buffer=io.BytesIO()
with tempfile.TemporaryDirectory(prefix='platform-backup-') as directory:
    target=Path(directory)/'journal.db'
    with sqlite3.connect('/var/lib/platform-healer/journal.db') as original,sqlite3.connect(target) as backup:original.backup(backup)
    with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
        for name in ('node.key','policy.json'):archive.add('/etc/platform-healer/'+name,arcname=name)
        archive.add(target,arcname='journal.db')
        for path in sorted(Path('/var/lib/platform-healer').glob('experiment-*/evidence.json')):archive.add(path,arcname='experiments/'+path.parent.name+'.json')
sys.stdout.buffer.write(buffer.getvalue())
'''
    (destination/'node-private.tgz').write_bytes(admin.run('k8s-worker-2','sudo python3 -',program.encode()))
    code="import sqlite3,sys; from pathlib import Path; source=sqlite3.connect('/state/knowledge.db'); target=sqlite3.connect('/state/recovery.db'); source.backup(target); target.close(); source.close(); sys.stdout.buffer.write(Path('/state/recovery.db').read_bytes())"
    command='sudo k3s kubectl -n platform-healer exec deployment/platform-controller -- python -c '+shlex.quote(code)
    (destination/'knowledge.db').write_bytes(admin.run('k8s-control',command))
    (destination/'operator.token').write_bytes((Path.home()/'.config/platform-healer/operator.token').read_bytes())
    for path in destination.iterdir():path.chmod(0o600)
    print('Private recovery directory:',destination)


if __name__=='__main__':main()
