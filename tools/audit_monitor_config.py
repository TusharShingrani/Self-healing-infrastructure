"""Validate candidate monitor files in a temporary directory; no live config changes."""
import base64
import json
import os
import shlex
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mapek.cloudstack import CloudStack
from mapek.educloud import EduCloudWorld, load_lab

lab=load_lab()
node=EduCloudWorld(CloudStack(project=lab['project_id']),'monitor',lab,
                   key_path=os.environ['LAB_SSH_KEY'])
vm=node._refresh()
if not vm or vm.get('projectid')!=lab['project_id'] or node.cs.ip_of(vm)!=lab['addresses']['monitor']:
    raise RuntimeError('Monitor identity unproven')
root=Path(__file__).resolve().parents[1]
payload={name:base64.b64encode((root/name).read_bytes()).decode() for name in
         ('monitoring/prometheus.yml','monitoring/blackbox.yml','monitoring/rules/healer.yml')}
code='''
import base64, subprocess, tempfile, yaml
from pathlib import Path
files=PAYLOAD
with tempfile.TemporaryDirectory(prefix='healer-config-audit-') as directory:
 root=Path(directory)
 for name,data in files.items():
  path=root/Path(name).name;path.write_bytes(base64.b64decode(data))
 config=yaml.safe_load((root/'prometheus.yml').read_text())
 config['rule_files']=[str(root/'healer.yml')]
 (root/'prometheus.yml').write_text(yaml.safe_dump(config))
 assert 'http_infrastructure' in yaml.safe_load((root/'blackbox.yml').read_text())['modules']
 subprocess.run(['promtool','check','rules',str(root/'healer.yml')],check=True)
 subprocess.run(['promtool','check','config',str(root/'prometheus.yml')],check=True)
 print('Candidate monitor files valid; live configuration unchanged')
'''.replace('PAYLOAD',repr(payload))
ok,out,err=node._probe('python3 -c '+shlex.quote(code))
print(out,err)
if not ok:raise RuntimeError('Candidate monitor configuration validation failed')
