"""Private lab PKI; key contents never enter Git, command arguments or logs."""
import os,subprocess
from pathlib import Path


def command(args):
    result=subprocess.run(['openssl',*args],capture_output=True)
    if result.returncode:raise RuntimeError('Private PKI operation failed; no key material printed')


def ensure_pki():
    root=Path.home()/'.config/platform-healer/pki';root.mkdir(mode=0o700,parents=True,exist_ok=True);root.chmod(0o700)
    if not (root/'ca.key').exists():
        command(['req','-x509','-newkey','ed25519','-nodes','-keyout',str(root/'ca.key'),'-out',str(root/'ca.crt'),'-days','365','-subj','/CN=platform-healer-private-lab-ca'])
    command(['x509','-checkend','604800','-noout','-in',str(root/'ca.crt')])
    definitions={
        'agent':('serverAuth','DNS:platform-agent.platform-healer-system.svc,DNS:platform-agent.platform-healer-system.svc.cluster.local,IP:10.1.1.80,IP:10.1.1.82'),
        'observer':('serverAuth','IP:10.1.1.84'),
        'controller':('clientAuth',None),'broker':('clientAuth',None),'monitor':('clientAuth',None)}
    for name,(usage,names) in definitions.items():
        if not (root/(name+'.crt')).exists():
            command(['req','-new','-newkey','ed25519','-nodes','-keyout',str(root/(name+'.key')),'-out',str(root/(name+'.csr')),'-subj','/CN=platform-'+name])
            extensions=root/(name+'.ext');extensions.write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage='+usage+'\n'+('subjectAltName='+names+'\n' if names else ''))
            command(['x509','-req','-in',str(root/(name+'.csr')),'-CA',str(root/'ca.crt'),'-CAkey',str(root/'ca.key'),'-CAcreateserial','-out',str(root/(name+'.crt')),'-days','90','-extfile',str(extensions)])
        command(['verify','-CAfile',str(root/'ca.crt'),str(root/(name+'.crt'))])
        command(['x509','-checkend','604800','-noout','-in',str(root/(name+'.crt'))])
    for path in root.iterdir():path.chmod(0o600)
    return root


def provision_hosts(admin,root):
    def write(node,path,data,group='root'):
        admin.run(node,'sudo install -d -m 750 -o root -g '+group+' '+str(Path(path).parent))
        admin.run(node,'sudo sh -c '+"'umask 077; cat > "+path+"'",data)
        admin.run(node,'sudo chown root:'+group+' '+path+' && sudo chmod 640 '+path)
    for name,node,directory,group in (
        ('broker','k8s-worker-2','/etc/platform-healer/tls','root'),
        ('observer','probe-1','/etc/platform-observer-tls','ubuntu'),
        ('monitor','monitor','/etc/prometheus/platform-tls','prometheus')):
        server=name=='observer'
        for filename,source in (('ca.crt','ca.crt'),('server.crt' if server else 'client.crt',name+'.crt'),('server.key' if server else 'client.key',name+'.key')):
            write(node,directory+'/'+filename,(root/source).read_bytes(),group)


if __name__=='__main__':print('Private PKI ready in administrator-only configuration directory:',ensure_pki())
