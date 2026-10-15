"""Explicit controlled lab faults. Never accepts shell commands or arbitrary targets."""
import argparse,copy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mapek.jobs import JobsWorld
from expansion import transport

FAULTS=('settings','workers','database','network','limits','compute')

def inject(world,fault):
    if fault not in FAULTS:raise ValueError('Unsupported fault')
    instances=world.ownership()
    if fault=='settings':world.kube.resource('configmaps','job-settings',{'data':{'DB_HOST':'10.1.1.99'}});world.restart_workloads()
    elif fault=='workers':world.kube.resource('deployments','job-worker',{'spec':{'replicas':0}})
    elif fault=='database':
        db=transport('db-1');ok,_,err=db._probe('sudo systemctl stop postgresql@16-main')
        if not ok:raise RuntimeError('Controlled database stop failed')
    elif fault=='network':
        # One temporary extra destination inside the owned isolated lab, never allow-all.
        policy=world.kube.resource('networkpolicies','job-database-egress');spec=copy.deepcopy(policy['spec'])
        spec['egress'].append({'to':[{'ipBlock':{'cidr':'10.1.1.50/32'}}],'ports':[{'protocol':'TCP','port':9090}]})
        world.kube.resource('networkpolicies','job-database-egress',{'spec':spec})
    elif fault=='limits':
        deployment=world.kube.resource('deployments','job-worker');spec=copy.deepcopy(deployment['spec']['template']['spec'])
        spec['containers'][0]['resources']['requests']['memory']='4Mi';spec['containers'][0]['resources']['limits']['memory']='8Mi'
        world.kube.resource('deployments','job-worker',{'spec':{'template':{'spec':spec}}})
    else:
        vm=instances['k8s-worker-1']
        if vm['state']!='Running':raise RuntimeError('Worker must start healthy before controlled node fault')
        world.cs.stop(vm['id'])  # Only this recorded stateless worker; never control/database/healer.

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('fault',choices=FAULTS);parser.add_argument('--controlled-experiment',action='store_true');args=parser.parse_args()
    if not args.controlled_experiment:parser.error('Confirm this is a controlled isolated-lab experiment with --controlled-experiment')
    world=JobsWorld();inject(world,args.fault);print('Controlled fault applied:',args.fault)
