"""Administrator deployment from the management VM; no CloudStack API needed.

Only administrator SSH can install the root broker. Runtime Pods do not inherit
this SSH identity. Install Docker on the builder and K3s on the nodes first.
"""
import argparse,base64,hashlib,io,json,re,secrets,subprocess,tarfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class Admin:
    def __init__(self,config):self.config=config;self.verified=set()
    def run(self,name,command,data=None,timeout=300):
        ip=self.config['nodes'][name]
        args=['ssh','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes',
              '-o','UserKnownHostsFile='+str(Path(self.config['known_hosts_directory']).expanduser()/ip),
              '-i',str(Path(self.config['ssh_key']).expanduser()),self.config['user']+'@'+ip]
        if name not in self.verified:
            result=subprocess.run(args+['hostname'],stdin=subprocess.DEVNULL,capture_output=True,check=True,timeout=20)
            if result.stdout.decode().strip()!=name:raise RuntimeError('Pinned node hostname mismatch')
            self.verified.add(name)
        stream={'input':data} if data is not None else {'stdin':subprocess.DEVNULL}
        result=subprocess.run(args+[command],capture_output=True,timeout=timeout,**stream)
        if result.returncode:raise RuntimeError(name+' refused operation; inspect node logs (no secret output printed)')
        return result.stdout


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default=str(ROOT/'config/educloud.json'))
    parser.add_argument('--bootstrap-gateway',action='store_true',help='Install the owned HAProxy namespace and independent observer')
    args=parser.parse_args();config=json.loads(Path(args.config).read_text());admin=Admin(config)
    from pki import ensure_pki,provision_hosts
    pki=ensure_pki();provision_hosts(admin,pki)
    if not re.fullmatch(r'python@sha256:[a-f0-9]{64}',config['base_image']):raise ValueError('Pinned Python image digest required')
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
        for base in ('src','host','experiments','manifests'):
            for path in sorted((ROOT/base).rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts:archive.add(path,arcname=str(path.relative_to(ROOT)),recursive=False)
        archive.add(ROOT/'Dockerfile',arcname='Dockerfile',recursive=False)
    source=buffer.getvalue();image='selfheal/platform:'+hashlib.sha256(source).hexdigest()[:16]
    for name in ('k8s-worker-1','k8s-worker-2','probe-1'):
        admin.run(name,'umask 077; cat > /home/ubuntu/platform-source.tgz',source)
        admin.run(name,'sudo install -d -m 755 /opt/platform-healer && sudo tar xzf /home/ubuntu/platform-source.tgz -C /opt/platform-healer && sudo chown -R root:root /opt/platform-healer')
    if args.bootstrap_gateway:
        admin.run('k8s-worker-2','sudo bash /opt/platform-healer/host/bootstrap-gateway.sh',timeout=180)
        admin.run('probe-1','sudo bash /opt/platform-healer/host/bootstrap-observer.sh')
    admin.run('probe-1','sudo systemctl restart platform-gateway-observer')
    admin.run('k8s-worker-2','sudo systemctl restart platform-healer-broker')
    admin.run('k8s-worker-1','cd /opt/platform-healer && sudo docker build --build-arg BASE='+config['base_image']+' -t '+image+' . >/home/ubuntu/platform-build.log 2>&1 && sudo docker save '+image+' -o /home/ubuntu/platform-image.tar && sudo chmod 644 /home/ubuntu/platform-image.tar')
    image_bytes=admin.run('k8s-worker-1','cat /home/ubuntu/platform-image.tar')
    admin.run('k8s-worker-2','cat > /home/ubuntu/platform-image.tar',image_bytes)
    for name in ('k8s-worker-1','k8s-worker-2'):admin.run(name,'sudo k3s ctr images import /home/ubuntu/platform-image.tar')
    manifest=json.loads(admin.run('k8s-worker-1','python3 /opt/platform-healer/manifests/render.py '+image))
    def apply(items):
        admin.run('k8s-control','sudo k3s kubectl apply -f -',json.dumps({'apiVersion':'v1','kind':'List','items':items}).encode())
    apply([x for x in manifest['items'] if x['kind']=='Namespace'])
    key=admin.run('k8s-worker-2','sudo cat /etc/platform-healer/node.key')
    private=Path.home()/'.config/platform-healer';private.mkdir(mode=0o700,exist_ok=True)
    token_path=private/'operator.token'
    if not token_path.exists():token_path.write_text(secrets.token_urlsafe(36));token_path.chmod(0o600)
    controller_data={'node.key':key,'operator.token':token_path.read_bytes(),
        'client.crt':(pki/'controller.crt').read_bytes(),'client.key':(pki/'controller.key').read_bytes(),'ca.crt':(pki/'ca.crt').read_bytes()}
    agent_data={'server.crt':(pki/'agent.crt').read_bytes(),'server.key':(pki/'agent.key').read_bytes(),'ca.crt':(pki/'ca.crt').read_bytes()}
    apply([{'apiVersion':'v1','kind':'Secret','metadata':{'name':name,'namespace':namespace},'type':'Opaque',
        'data':{key:base64.b64encode(value).decode() for key,value in values.items()}}
        for name,namespace,values in (('controller-keys','platform-healer',controller_data),('agent-tls','platform-healer-system',agent_data))])
    apply([x for x in manifest['items'] if x['kind']!='Namespace'])
    admin.run('k8s-control','sudo k3s kubectl -n platform-healer-system rollout status daemonset/platform-agent --timeout=120s && sudo k3s kubectl -n platform-healer rollout status deployment/platform-controller --timeout=120s')
    print('Native components ready:',image)
    print('Private operator token file:',token_path)


if __name__=='__main__':main()
