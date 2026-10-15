"""Project-scoped idempotent deployment and pinned transport for new lab nodes.

No destroy/reset/reboot command is provided. Reuse requires exact saved VM
identity, project, address and template; an existing unrecorded VM is refused.
"""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mapek.cloudstack import CloudStack
from mapek.educloud import EduCloudWorld,load_lab

ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/'config/jobs-lab.json').read_text())
STATE=ROOT/'state/expansion.json'

def transport(name):
    if name not in CONFIG['nodes']:raise ValueError('Node outside expansion allowlist')
    lab=load_lab();cs=CloudStack(project=lab['project_id'])
    vm=cs.instance(name);record=json.loads(STATE.read_text()).get(name,{})
    expected=CONFIG['nodes'][name]['address']
    if not vm or vm.get('id')!=record.get('id') or vm.get('projectid')!=lab['project_id'] or cs.ip_of(vm)!=expected or vm.get('templateid')!=lab['template_id']:
        raise RuntimeError('Expansion ownership/identity/address/template unproven: '+name)
    world=EduCloudWorld(cs,name,lab,key_path=os.environ['LAB_SSH_KEY'])
    world._refresh()
    if not world._ssh.reachable():raise RuntimeError('Pinned SSH unavailable: '+name)
    return world

def deploy():
    lab=load_lab();cs=CloudStack(project=lab['project_id'])
    STATE.parent.mkdir(exist_ok=True)
    state=json.loads(STATE.read_text()) if STATE.exists() else {}
    # Resume a submitted async job before deciding whether a name is unowned.
    for name,record in state.items():
        if not record.get('id') and record.get('job'):
            result=cs.wait(record['job'],label='resume deploy '+name)
            vm=result.get('virtualmachine',result)
            if not vm.get('id'):raise RuntimeError('Submitted deployment identity still unproven')
            record['id']=vm['id'];STATE.write_text(json.dumps(state,indent=2))
    projects=cs.call('listProjects',scoped=False,id=lab['project_id'])['project']
    if len(projects)!=1:raise RuntimeError('Project quota unproven')
    project=projects[0]
    existing={v['name']:v for v in cs.instances()}
    missing=[n for n in CONFIG['nodes'] if n not in state]
    required_ram=sum(4096 if n=='db-1' else 1024 if n=='probe-1' else 6144 for n in missing)
    if int(project['vmavailable'])<len(missing) or int(project['memoryavailable'])<required_ram:
        raise RuntimeError('Insufficient confirmed project headroom')
    jobs={}
    for name,spec in CONFIG['nodes'].items():
        if name in existing:
            if name not in state or state[name].get('id')!=existing[name]['id']:raise RuntimeError('Unrecorded existing target: '+name)
            continue
        if name in state and state[name].get('id'):raise RuntimeError('Recorded VM disappeared; investigate before replacement')
        if any(cs.ip_of(v)==spec['address'] for v in existing.values()):raise RuntimeError('Address already occupied')
        response=cs.call('deployVirtualMachine',name=name,displayname=name,templateid=lab['template_id'],zoneid=lab['zone_id'],
                         serviceofferingid=spec['offering'],networkids=lab['network_id'],keypair=lab['keypair'],ipaddress=spec['address'])
        state[name]={'job':response};STATE.write_text(json.dumps(state,indent=2))
        jobs[name]=response
    for name,record in state.items():
        if not record.get('id'):
            result=cs.wait(record['job'],label='deploy '+name)
            vm=result.get('virtualmachine',result)
            if not vm.get('id'):raise RuntimeError('Deployment did not return VM identity')
            record['id']=vm['id'];STATE.write_text(json.dumps(state,indent=2))
        spec=CONFIG['nodes'][name]
        world=EduCloudWorld(cs,name,lab,key_path=os.environ['LAB_SSH_KEY'])
        if not world.wait_until_ready(limit=600,poll=5):raise RuntimeError('SSH readiness failed: '+name)
        transport(name)
        print(name,'ready',spec['address'],flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['deploy','status']);args=parser.parse_args()
    if args.command=='deploy':deploy()
    else:
        for name in CONFIG['nodes']:
            world=transport(name);print(name,world._vm['id'],world._ssh.host)
