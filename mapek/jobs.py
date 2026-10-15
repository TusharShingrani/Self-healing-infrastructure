"""Reviewed repairs for a real job workflow; Kubernetes owns ordinary Pod recovery."""
import hashlib,json,os,time,urllib.request,urllib.error
from pathlib import Path
from .actions import CATALOGUE
from .cloudstack import CloudStack
from .educloud import ProtectedTarget,load_lab
from .infrastructure import InvestigationOperator,InvestigatedAnalyser
from .kubernetes import Kubernetes
from .operator import encode

ROOT=Path(__file__).resolve().parents[1]
ADAPTER_DIGEST=hashlib.sha256(b''.join(path.read_bytes() for path in (Path(__file__),ROOT/'mapek/kubernetes.py',ROOT/'tools/job-host/probe.py'))).hexdigest()
VERIFIER_DIGEST=hashlib.sha256((ROOT/'tools/job-host/probe.py').read_bytes()).hexdigest()
CONFIG=json.loads((ROOT/'config/jobs-lab.json').read_text())
REQUIRED={'settings','api_ready','worker_capacity','database','workload_contract','network_policy','policy_effective','worker_nodes','worker_processing','integrity','namespace_security'}
OPERATIONS={('restore_settings','job-settings'),('restore_replicas','job-worker'),('start_database','db-1'),
            ('restore_network','jobs-lab'),('restore_template','job-workloads'),('start_workers','worker-vms')}

def subset(expected,actual):
    if isinstance(expected,dict):return isinstance(actual,dict) and all(k in actual and subset(v,actual[k]) for k,v in expected.items())
    if isinstance(expected,list):return isinstance(actual,list) and len(expected)==len(actual) and all(subset(a,b) for a,b in zip(expected,actual))
    return expected==actual

def fetch(url):
    with urllib.request.urlopen(url,timeout=5) as response:
        data=json.load(response)
    if not isinstance(data,dict):raise ValueError('Invalid independent probe')
    return data

class JobRecipeBook:
    def __init__(self,specs=None):
        specs=json.loads((ROOT/'config/job-repair-recipes.json').read_text()) if specs is None else specs
        self.recipes={}
        for spec in specs:
            if set(spec)!={'id','operations','verify'} or spec['id'] in self.recipes or not spec['id'].startswith('job_'):
                raise ValueError('Invalid job recipe schema')
            if not 1<=len(spec['operations'])<=2:raise ValueError('Unbounded operation count')
            for step in spec['operations']:
                if set(step)!={'op','resource'} or (step['op'],step['resource']) not in OPERATIONS:raise ValueError('Unsupported job capability')
            if not isinstance(spec['verify'],list) or 'endpoint' not in spec['verify'] or not set(spec['verify'])<=REQUIRED|{'endpoint'}:
                raise ValueError('Job recipes require independent end-to-end verification')
            needed={'restore_settings':'settings','restore_replicas':'worker_capacity','start_database':'database',
                    'restore_network':'policy_effective','restore_template':'workload_contract','start_workers':'worker_nodes'}
            if any(needed[s['op']] not in spec['verify'] for s in spec['operations']):raise ValueError('Cause-specific verification missing')
            self.recipes[spec['id']]=spec
        self.digest=hashlib.sha256(encode(specs).encode()).hexdigest()
        for name in self.recipes:CATALOGUE['recipe_'+name]=lambda world,name=name:world.run_recipe(name)

class JobsWorld:
    def __init__(self):
        self.lab=load_lab().copy();self.lab['lab_instances']=['jobs-lab'];self.name='jobs-lab'
        self.service='job-processing';self.config_path='jobs-lab/job-settings';self.reference_dir='config/jobs-reference.json'
        self.log_mount=self.log_image=None;self.cs=CloudStack(project=self.lab['project_id']);self.kube=Kubernetes()
        self.recipes=JobRecipeBook();self.references=json.loads((ROOT/'config/jobs-reference.json').read_text())
        self.ids=json.loads((ROOT/'state/expansion.json').read_text());self._vm=None
        self.tick_count=self.downtime_ticks=0;self.latest={};self.last_action_at=0

    def ownership(self):
        instances={v.get('name'):v for v in self.cs.instances()}
        for name,spec in CONFIG['nodes'].items():
            vm=instances.get(name,{})
            if not vm or vm.get('id')!=self.ids[name].get('id') or vm.get('projectid')!=self.lab['project_id'] or self.cs.ip_of(vm)!=spec['address'] or vm.get('templateid')!=self.lab['template_id']:
                raise ProtectedTarget('Job-lab resource identity unproven: '+name)
        self._vm=instances['k8s-control'];return instances

    def observe(self,sample=True):
        obs={'tick':self.tick_count,'reachable':False,'service_running':None,'config_correct':None,'http_ok':None,
             'disk_percent':None,'disk_growth':None,'probe_error':'','monitor_source':'independent-job-client-and-kubernetes',
             'infrastructure_checks':{k:None for k in REQUIRED}}
        try:
            self.ownership()
            api=self.kube.resource('deployments','job-api');worker=self.kube.resource('deployments','job-worker');pods=self.kube.pods()
            namespace=self.kube.request('/api/v1/namespaces/jobs-lab')
            obs['namespace_uid']=namespace['metadata']['uid']
            obs['deployments']={d['metadata']['name']:{'uid':d['metadata']['uid'],'desired':d['spec'].get('replicas'),'ready':d.get('status',{}).get('readyReplicas',0)} for d in (api,worker)}
            settings=self.kube.resource('configmaps','job-settings')
            policies=self.kube.policies();policy_by_name={p['metadata']['name']:p for p in policies}
            obs['reachable']=True
            obs['service_running']=any(p['metadata'].get('labels',{}).get('app')=='job-api' and any('running' in c.get('state',{}) for c in p.get('status',{}).get('containerStatuses',[])) for p in pods)
            checks=obs['infrastructure_checks']
            labels=namespace['metadata'].get('labels',{})
            checks['namespace_security']=labels.get('pod-security.kubernetes.io/enforce')=='restricted' and labels.get('pod-security.kubernetes.io/enforce-version')=='v1.36'
            checks['settings']=settings.get('data')=={'DB_HOST':CONFIG['desired_db_host']}
            checks['api_ready']=api.get('status',{}).get('availableReplicas',0)>=1
            checks['worker_processing']=worker.get('status',{}).get('availableReplicas',0)>=1
            checks['worker_capacity']=worker['spec'].get('replicas')==CONFIG['expected_worker_replicas']
            desired_deployments={r['metadata']['name']:r for r in self.references if r['kind']=='Deployment'}
            checks['workload_contract']=all(subset(desired_deployments[d['metadata']['name']]['spec']['template']['spec'],d['spec']['template']['spec']) for d in (api,worker))
            desired_policies={r['metadata']['name']:r for r in self.references if r['kind']=='NetworkPolicy'}
            checks['network_policy']=set(policy_by_name)==set(desired_policies) and all(subset(r['spec'],policy_by_name.get(n,{}).get('spec')) for n,r in desired_policies.items())
            nodes=[self.kube.node(name) for name in ('k8s-worker-1','k8s-worker-2')]
            obs['node_uids']={n['metadata']['name']:n['metadata']['uid'] for n in nodes}
            checks['worker_nodes']=all(any(c['type']=='Ready' and c['status']=='True' for c in n.get('status',{}).get('conditions',[])) for n in nodes)
            db=fetch(CONFIG['database_metrics_url']+'/status');checks['database']=db.get('up')==1;obs['database']=db
            client=fetch(CONFIG['observer_url']+'/status');obs['client']=client
            if type(client.get('healthy')) is not bool or not isinstance(client.get('time'),(int,float)) or time.time()-client['time']>60:
                raise ValueError('Independent client observation missing or stale')
            obs['http_ok']=client['healthy']
            checks['integrity']=client.get('integrity_check') if type(client.get('integrity_check')) is bool else None
            witness=fetch('http://10.1.1.80:30081/status');obs['policy_witness']=witness
            # A blocked connection is proof only while the target is independently available.
            with urllib.request.urlopen('http://10.1.1.50:9090/-/ready',timeout=3) as response:monitor_available=response.status==200
            if not isinstance(witness.get('time'),(int,float)) or time.time()-witness['time']>20:raise ValueError('Policy witness stale')
            checks['policy_effective']=(monitor_available and witness.get('database_network_allowed') is True and witness.get('monitor_network_denied') is True) if checks['database'] else None
            obs['config_correct']=checks['settings'] and checks['workload_contract'] and checks['network_policy']
            obs['deployments']={d['metadata']['name']:{'uid':d['metadata']['uid'],'desired':d['spec'].get('replicas'),'ready':d.get('status',{}).get('readyReplicas',0)} for d in (api,worker)}
            obs['pods']=[{'name':p['metadata']['name'],'uid':p['metadata']['uid'],'node':p['spec'].get('nodeName'),'phase':p.get('status',{}).get('phase'),
                          'restarts':sum(c.get('restartCount',0) for c in p.get('status',{}).get('containerStatuses',[]))} for p in pods]
        except (OSError,ValueError,RuntimeError,KeyError,TypeError) as error:obs['probe_error']=f'{type(error).__name__}: {error}'[:300]
        if not obs['probe_error'] and any(v is None and not (k=='integrity' and obs.get('http_ok') is False) and not (k=='policy_effective' and obs['infrastructure_checks'].get('database') is False) for k,v in obs['infrastructure_checks'].items()):obs['probe_error']='Required independent check unreadable'
        self.latest=obs;return obs

    def health(self,obs=None):
        obs=self.observe(False) if obs is None else obs
        return not obs.get('probe_error') and all(obs.get(k) is True for k in ('reachable','service_running','config_correct','http_ok')) and all(obs.get('infrastructure_checks',{}).get(k) is True for k in REQUIRED)

    def step(self):self.tick_count+=1
    def note_health(self,healthy):self.downtime_ticks+=int(not healthy)

    def repair_identity(self):
        if not self.latest.get('namespace_uid') or len(self.latest.get('deployments',{}))!=2 or len(self.latest.get('node_uids',{}))!=2:
            return {'references':None,'live_config':None}
        identities={'vms':{n:r.get('id') for n,r in self.ids.items()},'deployments':{n:d['uid'] for n,d in self.latest.get('deployments',{}).items()},'namespace':self.latest.get('namespace_uid'),'nodes':self.latest.get('node_uids')}
        references=[hashlib.sha256(encode(self.references).encode()).hexdigest(),self.recipes.digest,ADAPTER_DIGEST,'fresh-independent-job-v2',encode(identities)]
        stable={k:v for k,v in self.latest.get('infrastructure_checks',{}).items() if k not in ('integrity','api_ready','worker_processing','policy_effective')}
        return {'references':references,'live_config':hashlib.sha256(encode(stable).encode()).hexdigest()}

    def diagnostic_evidence(self):
        return {'observation':self.latest,'service_requirement':'Accepted job completes with correct durable SHA-256 result within 30 seconds; policy remains restrictive',
                'locations':{'settings':'jobs-lab/configmap/job-settings','workers':'jobs-lab/deployment/job-worker','database':'db-1 PostgreSQL jobs_lab','network':'jobs-lab NetworkPolicy'},
                'references':self.repair_identity()['references']}

    def restart_workloads(self):
        for name in ('job-api','job-worker'):
            self.kube.resource('deployments',name,{'spec':{'template':{'metadata':{'annotations':{'selfheal/restarted-at':str(time.time())}}}}})

    def run_recipe(self,name):
        self.ownership();spec=self.recipes.recipes[name];self.last_action_at=time.time()
        for step in spec['operations']:
            op=step['op']
            if op=='restore_settings':
                self.kube.resource('configmaps','job-settings',{'data':{'DB_HOST':CONFIG['desired_db_host']}});self.restart_workloads()
            elif op=='restore_replicas':self.kube.resource('deployments','job-worker',{'spec':{'replicas':CONFIG['expected_worker_replicas']}})
            elif op=='restore_network':
                for ref in self.references:
                    if ref['kind']=='NetworkPolicy':self.kube.resource('networkpolicies',ref['metadata']['name'],{'spec':ref['spec']})
            elif op=='restore_template':
                for ref in self.references:
                    if ref['kind']=='Deployment' and ref['metadata']['name'] in ('job-api','job-worker'):
                        self.kube.resource('deployments',ref['metadata']['name'],{'spec':{'template':ref['spec']['template']}})
            elif op=='start_database':
                from tools.expansion import transport
                db=transport('db-1');ok,_,err=db._probe('sudo systemctl start postgresql@16-main')
                if not ok:return False,'Database start failed: '+err[:200]
            elif op=='start_workers':
                from tools.expansion import transport
                instances=self.ownership()
                for node in ('k8s-worker-1','k8s-worker-2'):
                    vm=instances[node]
                    if vm['state']=='Stopped':self.cs.start(vm['id'])
                    elif vm['state']!='Running':return False,'Worker transitional; wait for operator review'
                    deadline=time.monotonic()+120
                    while True:
                        try:world=transport(node);break
                        except RuntimeError as error:
                            if not str(error).startswith('Pinned SSH unavailable') or time.monotonic()>deadline:return False,'Worker identity/SSH readiness did not verify'
                            time.sleep(3)
                    ok,_,_=world._probe('sudo systemctl start k3s-agent')
                    if not ok:return False,'Worker agent could not start'
            else:raise ProtectedTarget('Unknown job capability')
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            ok,checks=self.recipe_verified(name)
            if ok:return True,encode(checks)
            time.sleep(3)
        return False,'Job repair failed fresh end-to-end or cause verification'

    def recipe_verified(self,name):
        obs=self.observe(False)
        structural=all(obs['infrastructure_checks'].get(k) is True for k in REQUIRED-{'integrity'})
        if structural and obs.get('reachable') and obs.get('service_running') and obs.get('config_correct') and not obs.get('probe_error'):
            # A cached pre-repair healthy sample is never proof of recovery.
            # Submit/read back a NEW job from the independent observer VM.
            from tools.expansion import transport
            observer=transport('probe-1');observer._ssh.timeout=60
            ok,digest,_=observer._probe('sha256sum /opt/healer-jobs/probe.py')
            if not ok or digest.split()[0]!=VERIFIER_DIGEST:
                obs['probe_error']='Independent verifier bytes differ from the reviewed contract'
                self.latest=obs
                return False,{'endpoint':False,'reviewed_verifier':False}
            ok,out,_=observer._probe('sudo -u job-probe python3 /opt/healer-jobs/probe.py --once')
            if ok:
                try:
                    fresh=json.loads(out)
                    if fresh.get('time',0)>=self.last_action_at:
                        obs['client']=fresh;obs['http_ok']=fresh.get('healthy') is True
                        obs['infrastructure_checks']['integrity']=fresh.get('integrity_check') is True
                except (ValueError,TypeError):obs['probe_error']='Fresh observer verification unreadable'
            else:obs['probe_error']='Fresh observer verification failed'
        self.latest=obs
        checks=dict(obs['infrastructure_checks'],endpoint=self.health(obs))
        wanted=self.recipes.recipes[name]['verify']
        return all(checks.get(k) is True for k in wanted),{k:checks.get(k) for k in wanted}

    def reboot_instance(self):raise ProtectedTarget('Job lab never permits destructive platform repairs')
    rebuild_instance=reboot_instance

class JobsOperator(InvestigationOperator):
    def verify(self,world,actions):
        checks={}
        for action in actions:
            if not action.startswith('recipe_job_') or action[7:] not in world.recipes.recipes:
                return False,{'observation':world.observe(False),'checks':{'supported_job_recipe':False}}
            ok,detail=world.recipe_verified(action[7:]);checks[action]=detail
        passed=bool(checks) and all(all(v is True for v in detail.values()) for detail in checks.values()) and world.health(world.latest)
        return passed,{'observation':world.latest,'checks':{'fresh_independent_job_and_cause_checks':passed},'recipe_checks':checks}
