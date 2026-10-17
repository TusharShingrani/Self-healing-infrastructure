import sys,time,tempfile,unittest,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from platform_healer.model import Sample,intent,authenticate
from platform_healer.analyse import analyse,Diagnosis
from platform_healer.leases import Broker
from platform_healer.knowledge import Knowledge

class Fake:
    action='raise_nofile_soft'
    def __init__(self):self.current=64;self.identity='same-process';self.safe=True;self.fail=False;self.changed=0
    def sample(self):return Sample('target','descriptors',self.identity,100,{})
    def value(self):return self.current
    def validate(self,value):
        if type(value)is not int or value not in (64,256):raise ValueError('Outside reviewed bounds')
        return value
    def apply(self,value):
        self.changed+=1
        if self.fail:raise OSError('injected failed syscall')
        self.current=value
    def rollback_ready(self,value):return self.safe

class BrokerTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.p=Fake();self.key=b'k'*32;self.clock=100;self.b=Broker(str(Path(self.temp.name)/'journal.db'),self.key,{'target':self.p},clock=lambda:self.clock)
    def tearDown(self):self.b.db.close();self.temp.cleanup()
    def message(self,**kwargs):return intent('target','same-process',self.p.action,64,{'value':256},'operator:1',self.key,now=100,**kwargs)
    def test_signed_bounded_action_and_idempotent_replay(self):
        m=self.message();self.assertEqual(self.b.execute(m)['status'],'applied');self.b.execute(m);self.assertEqual(self.p.changed,1)
    def test_invalid_signature_does_not_mutate(self):
        m=self.message();m['payload']['parameters']['value']=999
        with self.assertRaises(ValueError):self.b.execute(m)
        self.assertEqual(self.p.changed,0)
    def test_identity_change_refused(self):
        self.p.identity='replacement'
        with self.assertRaises(ValueError):self.b.execute(self.message())
    def test_stale_intent_refused(self):
        self.clock=200
        with self.assertRaises(ValueError):self.b.execute(self.message())
    def test_wrong_expected_value_refused(self):
        self.p.current=80
        with self.assertRaises(ValueError):self.b.execute(self.message())
    def test_wrong_target_refused(self):
        m=intent('other','same-process',self.p.action,64,{'value':256},'operator:1',self.key,now=100)
        with self.assertRaises(ValueError):self.b.execute(m)
    def test_out_of_bounds_refused(self):
        m=intent('target','same-process',self.p.action,64,{'value':999},'operator:1',self.key,now=100)
        with self.assertRaises(ValueError):self.b.execute(m)
    def test_active_lease_conflict_refused(self):
        self.b.execute(self.message());m=intent('target','same-process',self.p.action,256,{'value':256},'operator:2',self.key,now=100)
        with self.assertRaises(ValueError):self.b.execute(m)
    def test_expiry_rolls_back(self):
        m=self.message(lease=5);self.b.execute(m);self.clock=106;self.b.reconcile();self.assertEqual(self.p.current,64);self.assertEqual(self.b.operation(m['payload']['id'])['status'],'rolled_back')
    def test_administrator_change_is_preserved(self):
        m=self.message(lease=5);self.b.execute(m);self.p.current=128;self.clock=106;self.b.reconcile();self.assertEqual(self.p.current,128);self.assertEqual(self.b.operation(m['payload']['id'])['status'],'conflict')
    def test_busy_target_defers_rollback(self):
        m=self.message(lease=5);self.b.execute(m);self.p.safe=False;self.clock=106;self.b.reconcile();self.assertEqual(self.p.current,256);self.assertEqual(self.b.operation(m['payload']['id'])['status'],'rollback_deferred');self.p.safe=True;self.b.reconcile();self.assertEqual(self.p.current,64)
    def test_restart_recovers_lease_without_repeating_mutation(self):
        m=self.message();self.b.execute(m);self.b.db.close();self.b=Broker(str(Path(self.temp.name)/'journal.db'),self.key,{'target':self.p},clock=lambda:101);self.b.reconcile(recover=True);self.assertEqual(self.p.current,64)

class AnalysisTests(unittest.TestCase):
    def sample(self,errors=2,time_=100):return Sample('p','ports','ns',time_,{'used_ports':30,'range_size':32,'allocation_errors':errors,'successful_connections':30,'desired_connections':96})
    def test_high_occupancy_alone_does_not_diagnose(self):self.assertIsNone(analyse(self.sample(),self.sample(),100).action)
    def test_correlated_allocation_failure_diagnosed(self):self.assertEqual(analyse(self.sample(4),self.sample(2),100).action,'expand_port_range')
    def test_stale_is_unknown(self):self.assertEqual(analyse(self.sample(),now=200).cause,'unknown')
    def test_missing_is_unknown(self):self.assertEqual(analyse(Sample('p','ports','ns',100,{}),now=100).cause,'unknown')
    def test_descriptor_emfile_signature(self):
        a=Sample('p','descriptors','pid',100,{'open_fds':63,'soft_limit':64,'hard_limit':512,'allocation_errors':3,'held_fds':55,'desired_fds':128});b=Sample('p','descriptors','pid',99,dict(a.metrics,allocation_errors=2));self.assertEqual(analyse(a,b,100).action,'raise_nofile_soft')
    def test_unsupported_io_does_not_make_a_plan(self):self.assertIsNone(analyse(Sample('p','io','node',100,{'scheduler_supported':False}),now=100).action)
    def test_unknown_resource_kind_cannot_be_healthy(self):self.assertEqual(analyse(Sample('p','unexpected','node',100,{}),now=100).cause,'unknown')

class LearningTests(unittest.TestCase):
    def setUp(self):self.k=Knowledge(':memory:');self.s=Sample('target','descriptors','identity',100,{});self.d=Diagnosis('fd','raise_nofile_soft','EMFILE')
    def tearDown(self):self.k.db.close()
    def verified(self):
        c=self.k.capture(self.s,self.d);self.k.approve(c['id'],'reviewer','Reviewed bounded repair');self.k.outcome(c['id'],True,{'independent_probe':True});return c
    def test_first_incident_requires_approval(self):self.assertFalse(self.k.authorised(self.k.capture(self.s,self.d)))
    def test_single_occurrence_cannot_promote(self):
        c=self.verified()
        with self.assertRaises(ValueError):self.k.promote(c['scope'],c['cause'],c['action'],'reviewer')
    def test_two_distinct_verified_occurrences_allow_explicit_reuse(self):
        c=self.verified();self.verified();self.k.promote(c['scope'],c['cause'],c['action'],'reviewer');self.assertTrue(self.k.authorised(self.k.capture(self.s,self.d)))
    def test_scope_change_cannot_reuse(self):
        c=self.verified();self.verified();self.k.promote(c['scope'],c['cause'],c['action'],'reviewer');s=Sample('target','descriptors','replacement',100,{});self.assertFalse(self.k.authorised(self.k.capture(s,self.d)))
    def test_failed_verification_suspends(self):
        c=self.verified();self.verified();self.k.promote(c['scope'],c['cause'],c['action'],'reviewer');c=self.k.capture(self.s,self.d);self.k.outcome(c['id'],False,{});self.assertFalse(self.k.authorised(self.k.capture(self.s,self.d)))
    def test_unknown_has_no_executable_approval(self):
        c=self.k.capture(self.s,Diagnosis('unknown',None,'missing evidence'))
        with self.assertRaises(ValueError):self.k.approve(c['id'],'reviewer','Approve unknown arbitrary action')
    def test_unknown_occurrences_are_deduplicated(self):
        diagnosis=Diagnosis('unknown',None,'missing evidence')
        a=self.k.capture(self.s,diagnosis);b=self.k.capture(self.s,diagnosis)
        self.assertEqual(a['id'],b['id'])
    def test_restored_telemetry_resolves_unknown_without_deleting_evidence(self):
        c=self.k.capture(self.s,Diagnosis('unknown',None,'missing evidence'))
        self.k.resolve_unknown(self.s.target)
        self.assertEqual(self.k.export()['incidents'][0]['status'],'resolved')
        self.assertTrue(self.k.export()['audit'])

if __name__=='__main__':unittest.main()
