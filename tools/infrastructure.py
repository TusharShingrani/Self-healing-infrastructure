#!/usr/bin/env python3
"""Reviewed infrastructure laboratory: status, incidents, investigation, faults.

Run through tools/lab_shell.py on the healer. No arbitrary shell commands are
accepted. The loop uses a separate state directory from the nginx experiments.
"""
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mapek.cloudstack import CloudStack
from mapek.educloud import load_lab
from mapek.infrastructure import InfrastructureWorld, InvestigationOperator, InvestigatedAnalyser, ROOT, REDIS
from mapek.loop import Healer


def build(state='state/infrastructure', config='C'):
    os.makedirs(state, exist_ok=True)
    world = InfrastructureWorld(CloudStack(project=load_lab()['project_id']), load_lab(), os.environ.get('LAB_SSH_KEY'))
    operator = InvestigationOperator(os.path.join(state,'operator.db'))
    healer = Healer(world, config=config, knowledge_path=os.path.join(state,'knowledge.db'), auto_approve=False)
    healer.operator = operator
    healer.analyser = InvestigatedAnalyser(world, operator)
    if config == 'C' and os.environ.get('GEMINI_API_KEY'):
        from mapek.advisor import Advisor
        healer.advisor = Advisor(healer.knowledge)  # Evidence-based advice only.
    return world, operator, healer


def inject(world, fault):
    world.ownership()
    commands = {
        'dns_drift':('app-2', "sudo sed -i 's@address=/cache.lab.test/10.1.1.61@address=/cache.lab.test/10.1.1.62@' /etc/healer-stack/dns.conf && sudo systemctl restart healer-stack-dns"),
        'cache_budget':('app-2', 'test "$('+REDIS+' CONFIG SET maxmemory 1)" = OK'),
        'permissions':('app-1', 'test ! -L /var/lib/healer-stack/checkpoint && sudo chmod 400 /var/lib/healer-stack/checkpoint'),
        'cache_stop':('app-2', 'sudo systemctl stop healer-stack-redis'),
    }
    node, cmd = commands[fault]
    ok, out, err = world.command(node,cmd)
    if not ok:
        raise RuntimeError('Injection failed: '+err)
    return world.observe(False)


def install(world):
    world.ownership()
    # Transfer only tracked non-secret installer files; no SSH private keys.
    files = ['tools/install_infrastructure.sh','tools/stack-host/transaction.py']
    for node in ('app-2','app-1'):
        for file in files:
            data = base64.b64encode(Path(ROOT,file).read_bytes()).decode()
            dest = '/tmp/selfheal-infrastructure/'+file
            code = f"from pathlib import Path;import base64;p=Path({dest!r});p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode({data!r}))"
            import shlex
            ok, _, err = world.command(node, 'python3 -c '+shlex.quote(code))
            if not ok: raise RuntimeError(err)
        if node == 'app-1':
            # Transfer a restricted canary credential over pinned internal SSH.
            ok, client, err = world.command('app-2','sudo cat /etc/healer-stack/cache-client.json')
            if not ok: raise RuntimeError('Cannot transfer restricted cache credential')
            import shlex
            data=base64.b64encode(client.encode()).decode()
            code="import base64,os;from pathlib import Path;p=Path('/etc/healer-stack/cache-client.json');p.parent.mkdir(exist_ok=True);p.write_bytes(base64.b64decode("+repr(data)+"));os.chmod(p,0o640)"
            ok, _, err=world.command(node,'sudo python3 -c '+shlex.quote(code))
            if not ok:raise RuntimeError('Cannot install restricted cache credential')
        ok, out, err = world.command(node, f'bash /tmp/selfheal-infrastructure/tools/install_infrastructure.sh {node}')
        print(node, out, err, flush=True)
        if not ok: raise RuntimeError('Installer failed on '+node)
    obs = world.observe(False)
    if not world.health(obs): raise RuntimeError('Fresh infrastructure contract did not pass: '+json.dumps(obs))
    print(json.dumps(obs,indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state',default='state/infrastructure')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('status','install','list','procedures','export','tick'): sub.add_parser(name)
    run=sub.add_parser('run'); run.add_argument('--interval',type=float,default=10)
    show=sub.add_parser('show');show.add_argument('id',type=int)
    fault=sub.add_parser('inject');fault.add_argument('fault',choices=['dns_drift','cache_budget','permissions','cache_stop'])
    for name in ('investigate','approve','reject','record-human','promote'):
        c=sub.add_parser(name);c.add_argument('id',type=int);c.add_argument('--who',required=True)
        if name != 'promote': c.add_argument('--notes',required=True)
        if name in ('investigate','record-human'): c.add_argument('--recipe',required=True)
        if name == 'investigate': c.add_argument('--cause',required=True)
    args=p.parse_args()
    world, op, healer = build(args.state)
    if args.command == 'status': result=world.observe(False)
    elif args.command == 'install':install(world);return
    elif args.command == 'inject':result=inject(world,args.fault)
    elif args.command == 'list':result=op.cases()
    elif args.command == 'show':result=op.case(args.id)
    elif args.command == 'procedures':result=op.procedures()
    elif args.command == 'export':
        result={'cases':op.cases(),'procedures':op.procedures(),'audit':[dict(r) for r in op.db.execute('SELECT * FROM operator_audit ORDER BY id')]}
    elif args.command == 'investigate':
        result=op.investigate(world,args.id,args.cause,['recipe_'+args.recipe],args.who,args.notes)
    elif args.command in ('approve','reject'):
        result={'saved':op.decide(args.id,args.command=='approve',args.who,args.notes)}
    elif args.command == 'promote':op.promote(args.id,args.who);result={'promoted':args.id}
    elif args.command == 'record-human':
        world.observe(False)
        result={'verified':op.record_human(world,args.id,['recipe_'+args.recipe],args.who,args.notes)}
    elif args.command == 'tick':healer.tick();result=[e.__dict__ for e in healer.events]
    else:
        if args.interval < 5: raise ValueError('Minimum polling interval is five seconds')
        healer.verbose=True
        while True:
            healer.tick()
            with open(os.path.join(args.state,'events.jsonl'),'a') as out:
                out.write(json.dumps({'time':time.time(),'observation':world.latest,'events':[e.__dict__ for e in healer.events[-1:]]})+'\n')
            time.sleep(args.interval)
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
