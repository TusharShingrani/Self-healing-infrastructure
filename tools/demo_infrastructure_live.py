#!/usr/bin/env python3
"""Live mechanism validation, with SCRIPTED operator decisions, not an RCT.

Four faults, three occurrences each. Initial unknown -> investigation and
approved recipe -> separate manual repair -> promotion -> automatic recurrence.
No existing experiment results or nginx knowledge are reset.
"""
import json
import argparse
import subprocess
import time
from pathlib import Path
from infrastructure import build, inject

SCENARIOS = [
    ('dns_drift','dns_reference','dns_record_drift','DNS answer is .62 but the approved reference is .61'),
    ('cache_budget','cache_budget','cache_memory_limit_drift','SET returns OOM and effective maxmemory is one byte, not approved 64 MiB'),
    ('permissions','checkpoint_permissions','checkpoint_permission_drift','Checkpoint write fails with permission denied on the exact lab file'),
    ('cache_stop','cache_dependency','cache_dependency_stopped','Transaction remains running; app-2 Redis is inactive and its write connection fails'),
]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',default='state/infrastructure')
    parser.add_argument('--evidence',default='evidence/infrastructure-results.json')
    args=parser.parse_args()
    if subprocess.run(['systemctl','--user','is-active','--quiet','healer-infrastructure']).returncode==0:
        raise RuntimeError('Stop the dedicated infrastructure service before a controlled scripted exercise')
    world, operator, healer = build(args.state)
    if operator.cases():raise RuntimeError('Use a fresh explicitly chosen experiment state; existing evidence must not be overwritten')
    baseline=world.observe(False)
    if not world.health(baseline):raise RuntimeError('Baseline is not healthy')
    results={'started':time.time(),'protocol':'mechanism-validation; scripted investigator/operator; three occurrences per class',
             'baseline':baseline,'runs':[]}
    evidence=Path(args.evidence)
    if evidence.exists():raise RuntimeError('Existing evidence must not be overwritten; choose --evidence explicitly')
    evidence.parent.mkdir(parents=True,exist_ok=True)
    def save():evidence.write_text(json.dumps(results,indent=2)+'\n')
    def healthy_tick():
        time.sleep(10);healer.tick()
        if not world.health(world.latest):raise RuntimeError('Healthy interval failed')
    try:
        for fault,recipe,cause,rationale in SCENARIOS:
            for repetition in (1,2,3):
                action='recipe_'+recipe
                # Honour the actual tick guardrails; never disable cooldowns.
                while not healer.guardrails.check([action],world.tick_count+1)[0]:healthy_tick()
                if not world.health(world.observe(False)):raise RuntimeError('Fault baseline failed')
                start=time.time();obs=inject(world,fault)
                if world.health(obs):raise RuntimeError('Fault not confirmed')
                run={'fault':fault,'repetition':repetition,'injected_at':start,'failed_observation':obs}
                if repetition==1:
                    # Demonstrate why a frontend restart is an insufficient fix.
                    ok,_,err=world.command('app-1','sudo systemctl restart healer-stack-transaction')
                    time.sleep(.3)
                    after_restart=world.observe(False)
                    run['frontend_restart']={'command_success':ok,'healthy':world.health(after_restart),'observation':after_restart}
                    if world.health(after_restart):raise RuntimeError('Restart comparator unexpectedly repaired cause')
                detected=time.time();healer.tick();run['first_tick_completed_at']=time.time()
                run['detection_tick_seconds']=run['first_tick_completed_at']-detected
                run['events_before_decision']=[e.__dict__ for e in healer.events[-1:]]
                if repetition==1:
                    case=operator.cases()[0]
                    if case['cause']!='unknown':raise RuntimeError('First occurrence was not unknown')
                    case=operator.investigate(world,case['id'],cause,[action],'scripted-investigator',rationale)
                    operator.decide(case['id'],True,'scripted-operator','Reviewed bounded operations and cause-specific verification')
                    repair_started=time.time();healer.tick();run['mode']='investigated-approved'
                elif repetition==2:
                    case=operator.cases()[0]
                    if case['status']!='pending':raise RuntimeError('Second occurrence did not require review')
                    repair_started=time.time();ok,detail=world.run_recipe(recipe)
                    if not ok or not operator.record_human(world,case['id'],[action],'scripted-manual-operator','Applied the bounded recipe separately from loop execution; '+rationale):
                        raise RuntimeError('Manual repair did not independently verify')
                    run['mode']='recorded-manual'
                    proc=[p for p in operator.procedures() if p['cause']==cause][0]
                    operator.promote(proc['id'],'scripted-reviewer')
                else:
                    repair_started=detected;run['mode']='promoted-automatic'
                final=world.observe(False);run['recovered_at']=time.time()
                run['repair_and_verification_seconds']=run['recovered_at']-repair_started
                run['injection_to_verified_seconds']=run['recovered_at']-start
                run['after']=final
                case=operator.cases()[0];run['case_id']=case['id'];run['verified']=case['status']=='verified' and world.health(final)
                run['automatic_procedure_id']=case['procedure_id']
                if not run['verified'] or (repetition==3 and not case['procedure_id']):raise RuntimeError('Expected verified learning transition did not occur')
                results['runs'].append(run);save()
                print(json.dumps({k:run[k] for k in ('fault','repetition','mode','verified','repair_and_verification_seconds','automatic_procedure_id')}),flush=True)
                healer.tick()  # Observe recovery and reconcile cleared conditions.
        results['cases']=operator.cases();results['procedures']=operator.procedures()
        results['audit']=[dict(r) for r in operator.db.execute('SELECT * FROM operator_audit ORDER BY id')]
        results['finished']=time.time();results['final']=world.observe(False);save()
        print('All four unknown-investigation-learning chains verified live',flush=True)
    finally:
        # Restore each declared lab invariant even if a measurement fails.
        for _,recipe,_,_ in reversed(SCENARIOS):
            ok, detail=world.run_recipe(recipe)
            if not ok:print('CLEANUP FAILED',recipe,detail,flush=True)


if __name__=='__main__':main()
