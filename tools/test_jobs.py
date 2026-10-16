"""Job capabilities, identity and fail-closed health; no live API/VM calls."""
import copy,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mapek.jobs import JobsWorld,JobRecipeBook,REQUIRED,CONFIG,subset
from mapek.kubernetes import Kubernetes,KubernetesError
from mapek.educloud import ProtectedTarget

class Tests(unittest.TestCase):
    def test_every_recipe_has_supported_exact_operations(self):
        self.assertEqual(len(JobRecipeBook().recipes),6)
    def test_shell_recipe_refused(self):
        with self.assertRaises(ValueError):JobRecipeBook([{'id':'job_bad','operations':[{'op':'shell','resource':'db-1'}],'verify':['endpoint','database']}])
    def test_arbitrary_target_refused(self):
        with self.assertRaises(ValueError):JobRecipeBook([{'id':'job_bad','operations':[{'op':'start_database','resource':'healer-ubuntu'}],'verify':['database','endpoint']}])
    def test_missing_cause_check_refused(self):
        with self.assertRaises(ValueError):JobRecipeBook([{'id':'job_bad','operations':[{'op':'restore_network','resource':'jobs-lab'}],'verify':['endpoint']}])
    def test_duplicate_recipe_refused(self):
        spec=list(JobRecipeBook().recipes.values())[0]
        with self.assertRaises(ValueError):JobRecipeBook([spec,spec])
    def test_protected_destructive_repairs_never_execute(self):
        with self.assertRaises(ProtectedTarget):JobsWorld.reboot_instance(None)
        with self.assertRaises(ProtectedTarget):JobsWorld.rebuild_instance(None)
    def test_namespace_boundary_before_network(self):
        kube=Kubernetes.__new__(Kubernetes)
        with self.assertRaises(KubernetesError):kube.request('/api/v1/namespaces/kube-system/secrets')
    def test_traversal_boundary_before_network(self):
        kube=Kubernetes.__new__(Kubernetes)
        for path in ('/api/v1/namespaces/jobs-lab/../../secrets','/api/v1/namespaces/jobs-lab/%2e%2e/secrets'):
            with self.assertRaises(KubernetesError):kube.request(path)
    def test_unlisted_resource_before_network(self):
        kube=Kubernetes.__new__(Kubernetes)
        with self.assertRaises(KubernetesError):kube.resource('deployments','monitor',{'spec':{}})
    def test_wrong_node_before_network(self):
        with self.assertRaises(KubernetesError):Kubernetes.node(None,'healer-ubuntu')
    def test_wrong_project_fails_closed(self):
        w=JobsWorld.__new__(JobsWorld);w.lab={'project_id':'p','template_id':'t'}
        vms=[{'name':name,'id':name,'projectid':'p','templateid':'t','ip':spec['address']} for name,spec in CONFIG['nodes'].items()]
        w.ids={name:{'id':name} for name in CONFIG['nodes']}
        w.cs=SimpleNamespace(instances=lambda:vms,ip_of=lambda vm:vm['ip'])
        self.assertEqual(w.ownership()['db-1']['id'],'db-1')
        vms[0].pop('projectid')
        with self.assertRaises(ProtectedTarget):w.ownership()
    def test_changed_vm_identity_fails_closed(self):
        w=JobsWorld.__new__(JobsWorld);w.lab={'project_id':'p','template_id':'t'};w.ids={name:{'id':'expected'} for name in CONFIG['nodes']}
        w.cs=SimpleNamespace(instances=lambda:[{'name':'k8s-control','id':'wrong'}],ip_of=lambda vm:'10.1.1.80')
        with self.assertRaises(ProtectedTarget):w.ownership()
    def test_all_required_checks_must_pass(self):
        obs={'reachable':True,'service_running':True,'config_correct':True,'http_ok':True,'probe_error':'','infrastructure_checks':dict.fromkeys(REQUIRED,True)}
        self.assertTrue(JobsWorld.health(None,obs))
        for key in REQUIRED:
            for bad in (False,None):
                changed=copy.deepcopy(obs);changed['infrastructure_checks'][key]=bad
                self.assertFalse(JobsWorld.health(None,changed))
    def test_probe_error_overrides_healthy_checks(self):
        obs={'reachable':True,'service_running':True,'config_correct':True,'http_ok':True,'probe_error':'unreadable','infrastructure_checks':dict.fromkeys(REQUIRED,True)}
        self.assertFalse(JobsWorld.health(None,obs))
    def test_missing_kubernetes_identity_cannot_validate(self):
        world=SimpleNamespace(latest={})
        self.assertIsNone(JobsWorld.repair_identity(world)['references'])
    def test_changed_deployment_uid_changes_scope(self):
        world=SimpleNamespace(latest={'namespace_uid':'ns','deployments':{'job-api':{'uid':'a'},'job-worker':{'uid':'b'}},'node_uids':{'n1':'1','n2':'2'},'infrastructure_checks':{}},
                              ids={'vm':{'id':'v'}},references=[],recipes=SimpleNamespace(digest='d'))
        before=JobsWorld.repair_identity(world)['references'];world.latest['deployments']['job-api']['uid']='replacement'
        self.assertNotEqual(before,JobsWorld.repair_identity(world)['references'])
    def test_changed_namespace_uid_changes_scope(self):
        world=SimpleNamespace(latest={'namespace_uid':'ns','deployments':{'job-api':{'uid':'a'},'job-worker':{'uid':'b'}},'node_uids':{'n1':'1','n2':'2'},'infrastructure_checks':{}},
                              ids={},references=[],recipes=SimpleNamespace(digest='d'))
        before=JobsWorld.repair_identity(world)['references'];world.latest['namespace_uid']='replacement'
        self.assertNotEqual(before,JobsWorld.repair_identity(world)['references'])
    def test_template_mismatch_does_not_pass(self):
        self.assertFalse(subset({'containers':[{'image':'approved','resources':{'limits':{'memory':'128Mi'}}}]},{'containers':[{'image':'wrong','resources':{'limits':{'memory':'128Mi'}}}]}))
    def test_capacity_or_privilege_change_does_not_pass(self):
        self.assertFalse(subset({'securityContext':{'allowPrivilegeEscalation':False}},{'securityContext':{'allowPrivilegeEscalation':True}}))
    def test_promotion_selects_exact_scope_not_first_cause_name(self):
        from demo_jobs_live import matching_procedure
        case={'scope':'new','cause':'same','symptoms':'s','actions':'a'}
        old=dict(case,scope='old',id=1);new=dict(case,id=2)
        self.assertEqual(matching_procedure([old,new],case)['id'],2)
        with self.assertRaises(RuntimeError):matching_procedure([old],case)

class BankPolicyTests(unittest.TestCase):
    def test_integrity_incident_refuses_configuration_actions_before_mutation(self):
        from unittest.mock import Mock
        for recipe in ('job_config','job_workers','job_template'):
            world=SimpleNamespace(ownership=Mock(return_value={}),latest={'infrastructure_checks':{'integrity':False}},kube=Mock())
            ok,detail=JobsWorld.run_recipe(world,recipe)
            self.assertFalse(ok)
            self.assertIn('integrity incident',detail)
            world.kube.resource.assert_not_called()

    def test_database_node_and_network_procedures_cannot_be_promoted(self):
        from mapek.jobs import JobsOperator
        for action in ('recipe_job_database','recipe_job_compute','recipe_job_network'):
            op=JobsOperator(':memory:')
            op.db.execute("INSERT INTO procedures(id,scope,cause,symptoms,actions,status,created) VALUES(1,'{}','known','[]',?,'candidate',0)",(json.dumps([action]),));op.db.commit()
            with self.assertRaises(ValueError):op.promote(1,'reviewer')

if __name__=='__main__':unittest.main(verbosity=2)
