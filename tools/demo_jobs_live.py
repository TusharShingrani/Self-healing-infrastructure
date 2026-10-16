"""Real job learning workflow: scripted operator roles, independent verification.

Three core cause-directed repairs, ten occurrences each by default. First reviewed and
approved, second separately applied and recorded, third promoted automatic.
Existing Knowledge and incident evidence are preserved. No protected VM stops.
"""
import argparse,json,subprocess,time,urllib.request
from pathlib import Path
from jobs import build
from job_faults import inject
from mapek.stages import Monitor

SCENARIOS=[('settings','job_config','job_database_endpoint_drift'),('workers','job_workers','job_worker_capacity_drift'),
           ('database','job_database','job_database_service_stopped'),('network','job_network','job_network_policy_drift'),
           ('limits','job_template','job_worker_resource_limit_drift'),('compute','job_compute','job_worker_compute_stopped')]

def matching_procedure(procedures,case):
    matches=[p for p in procedures if all(p[k]==case[k] for k in ('scope','cause','symptoms','actions'))]
    if len(matches)!=1:raise RuntimeError('Exactly one procedure for the verified incident scope is required')
    return matches[0]

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fault',choices=[s[0] for s in SCENARIOS]);parser.add_argument('--repetitions',type=int,choices=range(3,11),default=10);parser.add_argument('--output',default='state/bank-learning.json');args=parser.parse_args()
    output=Path(args.output)
    if output.exists():raise RuntimeError('Preserve existing evidence; use a fresh output path')
    output.parent.mkdir(exist_ok=True)
    pause=Path('state/jobs/paused')
    if pause.exists():raise RuntimeError('Existing operator pause; preserve it and investigate before a controlled exercise')
    pause.parent.mkdir(parents=True,exist_ok=True);pause.touch()
    subprocess.run(['systemctl','--user','restart','healer-jobs'],check=True)
    deadline=time.monotonic()+40
    while time.monotonic()<deadline:
        try:
            with urllib.request.urlopen('http://10.1.1.205:9109/status',timeout=3) as response:paused=json.load(response).get('paused') is True
            if paused:break
        except (OSError,ValueError):pass
        time.sleep(2)
    else:pause.unlink();raise RuntimeError('Observe-only service did not verify before fault injection')
    w,op,h=build();results={'started':time.time(),'protocol':'scripted investigator/operator; independent job receipts and cause checks; normal cooldowns','initial_cases':op.cases(),'initial_procedures':op.procedures(),'runs':[]}
    active=None
    def save():output.write_text(json.dumps(results,indent=2)+'\n')
    def settle_failure(fault):
        required={'settings':'settings','workers':'worker_capacity','database':'database','network':'policy_effective','limits':'workload_contract','compute':'worker_nodes'}[fault]
        previous=None;stable=0;deadline=time.monotonic()+100
        while time.monotonic()<deadline:
            obs=w.observe(False);symptoms=Monitor().symptoms(obs)
            signature=(tuple(sorted(symptoms)),obs.get('http_ok'),obs.get('service_running'),obs.get('config_correct'))
            # RollingUpdate may retain healthy old Pods when a new configuration
            # is bad. That is genuine native availability protection, not a failed
            # injection. Only scaling all workers to zero must cause a job outage.
            client_measured=type(obs.get('http_ok')) is bool and obs.get('client',{}).get('time',0)>=started
            expected_impact=obs.get('http_ok') is False if fault=='workers' else client_measured
            if obs['infrastructure_checks'].get(required) is False and (not obs.get('probe_error') or fault=='compute') and client_measured and expected_impact and signature==previous:stable+=1
            else:stable=0
            previous=signature
            if stable>=3:return obs
            time.sleep(3)
        raise RuntimeError('Fault evidence did not settle; refusing to approve uncertain observations')
    try:
        if not w.health(w.observe(False)):raise RuntimeError('Job baseline unhealthy')
        for fault,recipe,cause in SCENARIOS:
            if args.fault and fault!=args.fault:continue
            if not args.fault and fault not in ('settings','workers','limits'):continue
            _,current_scope=op.context(w,[],'unknown',[],w.latest)
            if any(p['cause']==cause and p['status']=='validated' and p['scope']==current_scope for p in op.procedures()):raise RuntimeError('Already validated in this scope; select fresh experimental state rather than pretend to learn again')
            for repetition in range(1,args.repetitions+1):
                action='recipe_'+recipe
                while not h.guardrails.check([action],w.tick_count+1)[0]:h.tick();time.sleep(10)
                if not w.health(w.observe(False)):raise RuntimeError('Healthy interval failed')
                active=recipe;started=time.time();inject(w,fault);before=settle_failure(fault)
                h.tick();case=op.cases()[0]
                if repetition==1:
                    if case['status']!='pending':raise RuntimeError('First occurrence must wait for review')
                    if case['cause']=='unknown':
                        case=op.investigate(w,case['id'],cause,[action],'scripted-investigator','Compared controlled fault evidence with approved job contract; '+fault)
                        mode='investigated-approved'
                    elif case['cause']==cause and json.loads(case['actions'])==[action]:
                        mode='existing-investigation-approved'
                    else:raise RuntimeError('Existing diagnosis differs from the reviewed experiment plan')
                    if not op.decide(case['id'],True,'scripted-operator','Reviewed bounded '+recipe+' and independent job/security verification'):raise RuntimeError('Approval not saved')
                    h.tick()
                elif repetition==2:
                    if case['status']!='pending':raise RuntimeError('Separate occurrence must wait for review')
                    ok,detail=w.run_recipe(recipe)
                    if not ok or not op.record_human(w,case['id'],[action],'scripted-manual-operator','Applied reviewed bounded repair separately from loop; '+fault):raise RuntimeError('Separate repair did not verify')
                    proc=matching_procedure(op.procedures(),op.case(case['id']));op.promote(proc['id'],'scripted-reviewer');mode='recorded-human-and-promoted'
                else:mode='promoted-automatic'
                case=op.cases()[0];after=w.observe(False)
                if case['status']!='verified' or not w.health(after) or repetition>=3 and not case['procedure_id']:raise RuntimeError('Expected verified repair transition failed')
                run={'fault':fault,'repetition':repetition,'mode':mode,'case_id':case['id'],'automatic_procedure_id':case['procedure_id'],
                     'business_failure_observed':before.get('http_ok') is False,
                     'injection_time':started,'injection_to_verified_seconds':time.time()-started,'before':before,'after':after,'verified':True}
                results['runs'].append(run);save();print(json.dumps({k:run[k] for k in ('fault','repetition','mode','verified','injection_to_verified_seconds')}),flush=True)
                active=None;h.tick()
        results['finished']=time.time();results['cases']=op.cases();results['procedures']=op.procedures();results['final']=w.observe(False);results['outcome']='completed';save()
    except Exception as error:
        results['outcome']='failed';results['failure']=type(error).__name__+': '+str(error)[:300]
        results['cases']=op.cases();results['procedures']=op.procedures();save();raise
    finally:
        if active:
            ok,detail=w.run_recipe(active)
            if not ok:print('CLEANUP FAILED',active,detail,flush=True)
        pause.unlink(missing_ok=True)

if __name__=='__main__':main()
