"""Persistent terminal operator interface. Notes are never executed."""
import argparse
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapek.operator import Operator
from mapek.cloudstack import CloudStack
from mapek.educloud import EduCloudWorld, load_lab


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', default=os.environ.get('HEALER_STATE', 'state'))
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list'); sub.add_parser('procedures'); sub.add_parser('export'); sub.add_parser('audit')
    show = sub.add_parser('show'); show.add_argument('id', type=int)
    for name in ('approve', 'reject', 'record-human', 'promote'):
        p = sub.add_parser(name); p.add_argument('id', type=int)
        p.add_argument('--who', required=True)
        if name != 'promote': p.add_argument('--notes', required=True)
        if name == 'record-human': p.add_argument('--actions', nargs='+', required=True)
    args = parser.parse_args()
    os.makedirs(args.state, exist_ok=True)
    operator = Operator(os.path.join(args.state, 'operator.db'))
    if args.command == 'list':
        for c in operator.cases():
            print(f"#{c['id']} {c['target']} {c['status']} {c['cause']} actions={c['actions']}")
    elif args.command == 'show':
        c = operator.case(args.id)
        for k in ('evidence', 'after_evidence', 'scope', 'symptoms', 'actions'):
            if c[k]: c[k] = json.loads(c[k])
        print(json.dumps(c, indent=2))
    elif args.command == 'procedures':
        print(json.dumps(operator.procedures(), indent=2))
    elif args.command in ('audit', 'export'):
        audit = [dict(r) for r in operator.db.execute('SELECT * FROM operator_audit ORDER BY id')]
        print(json.dumps(audit if args.command == 'audit' else {'cases': operator.cases(), 'procedures': operator.procedures(), 'audit': audit}, indent=2))
    elif args.command in ('approve', 'reject'):
        print('decision saved' if operator.decide(args.id, args.command == 'approve', args.who, args.notes) else 'incident is not pending')
    elif args.command == 'promote':
        operator.promote(args.id, args.who); print('procedure validated for its recorded target and context')
    else:
        case = operator.case(args.id); lab = load_lab()
        if case['target'] not in lab['lab_instances']:
            raise ValueError('Not an allowed managed target')
        world = EduCloudWorld(CloudStack(project=lab['project_id']), case['target'], lab,
                              key_path=os.environ.get('LAB_SSH_KEY'))
        world.observe(sample=False)
        print('verified' if operator.record_human(world, args.id, args.actions, args.who, args.notes) else 'verification failed; nothing learned')


if __name__ == '__main__':
    try: main()
    except (ValueError, RuntimeError) as error: sys.exit(str(error))
