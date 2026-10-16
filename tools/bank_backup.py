"""Private PostgreSQL dump plus consistent controller-state copies. No publication."""
import argparse,base64,json,os,shlex,sqlite3,subprocess,time
from pathlib import Path
from expansion import transport,ROOT

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--label',required=True);args=parser.parse_args()
    if not args.label.replace('-','').isalnum():raise ValueError('Use an alphanumeric backup label')
    dest=Path.home()/'healer-upgrade-backups'/args.label
    if dest.exists():raise RuntimeError('Preserve existing backup; choose a fresh label')
    dest.mkdir(mode=0o700,parents=True)
    db=transport('db-1');db._ssh.timeout=180
    remote='/home/ubuntu/'+args.label+'.dump'
    command='umask 077; test ! -e '+shlex.quote(remote)+' && sudo -u postgres pg_dump -Fc jobs_lab > '+shlex.quote(remote)
    ok,_,_=db._probe(command)
    if not ok:raise RuntimeError('Database backup failed')
    subprocess.run(['scp','-q','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(Path.home()/'.ssh/healer-lab-known-hosts/10.1.1.83'),'-i',os.environ['LAB_SSH_KEY'],'-o','IdentitiesOnly=yes','ubuntu@10.1.1.83:'+remote,str(dest/'database.dump')],check=True)
    # Private trust and credentials are required to recover the service, not just its data.
    command="bash -o pipefail -c "+shlex.quote("sudo tar czf - -C / etc/healer-bank etc/healer-jobs/secrets.json | base64 -w0")
    ok,encoded,_=db._probe(command)
    if not ok:raise RuntimeError('Private database trust backup failed')
    (dest/'database-private.tgz').write_bytes(base64.b64decode(encoded,validate=True))
    paths=[str(Path.home()/'.config/healer-jobs'),str(Path.home()/'.config/healer-console'),str(Path.home()/'.ssh/healer-lab-known-hosts'),os.environ['LAB_SSH_KEY']]
    with (dest/'healer-private.tgz').open('wb') as archive:
        subprocess.run(['tar','czf','-',*paths],stdout=archive,stderr=subprocess.DEVNULL,check=True)
    for path in dest.iterdir():path.chmod(0o600)
    for name in ('operator','knowledge'):

        source=ROOT/'state/jobs'/ (name+'.db')
        if source.exists():
            with sqlite3.connect(source) as original,sqlite3.connect(dest/(name+'.db')) as target:original.backup(target)
    for name in ('config/jobs-reference.json','config/jobs-image.json','state/expansion.json'):
        p=ROOT/name
        if p.exists():(dest/p.name).write_bytes(p.read_bytes())
    print('Private backup completed:',str(dest))

if __name__=='__main__':main()
