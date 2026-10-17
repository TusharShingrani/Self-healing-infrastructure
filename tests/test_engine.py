import sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from platform_healer.engine import Engine
from platform_healer.knowledge import Knowledge
from platform_healer.model import Sample


class Remote:
    def __init__(self):self.errors=0;self.soft=64;self.identity='owned-process';self.operations={};self.calls=0;self.verify=True;self.timeout_after_apply=False
    def request(self,path,data=None):
        if path.startswith('/sample/'):
            return Sample('target','descriptors',self.identity,time.time(),dict(open_fds=63 if self.soft==64 else 135,
                soft_limit=self.soft,hard_limit=512,allocation_errors=self.errors,held_fds=55 if self.soft==64 else 128,desired_fds=128)).json()
        if path=='/execute':
            self.calls+=1;self.soft=256;self.operations[data['payload']['id']]={'status':'applied'}
            if self.timeout_after_apply:raise TimeoutError('Ambiguous transport outcome')
            return {'status':'applied'}
        if path.startswith('/operation/'):return self.operations[path.split('/')[-1]]
        if path.startswith('/verify/'):return {'verified':self.verify}
        raise AssertionError(path)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.k=Knowledge(':memory:');self.remote=Remote();self.cfg={'target':dict(client=self.remote,key=b'k'*32,baseline=64,expanded=256)};self.e=Engine(self.k,self.cfg)
    def tearDown(self):self.k.db.close()
    def incident(self):
        self.e.tick();self.remote.errors+=1;self.e.tick();return self.k.export()['incidents'][-1]
    def start(self):
        case=self.incident();self.e.approve(case['id'],'operator','Reviewed bounded EMFILE repair');self.remote.errors+=1;self.e.tick();return case
    def test_unapproved_incident_does_not_execute(self):self.incident();self.assertEqual(self.remote.calls,0)
    def test_approval_then_independent_verification(self):
        case=self.start();self.e.tick();self.assertEqual(self.k.export()['incidents'][-1]['status'],'verified');self.assertEqual(self.remote.calls,1)
    def test_transport_timeout_reconciles_without_second_execution(self):
        self.remote.timeout_after_apply=True;self.start();self.e.tick();self.assertEqual(self.remote.calls,1);self.assertEqual(self.k.export()['incidents'][-1]['status'],'verified')
    def test_failed_probe_does_not_verify(self):
        self.remote.verify=False;self.start();self.e.tick();self.assertEqual(self.k.export()['incidents'][-1]['status'],'executing')
    def test_verification_deadline_records_failure(self):
        self.remote.verify=False;self.start();self.k.db.execute('UPDATE executions SET deadline=0');self.k.db.commit();self.e.tick();self.assertEqual(self.k.export()['incidents'][0]['status'],'failed')
    def test_replacement_identity_cannot_verify_old_action(self):
        self.start();self.remote.identity='replacement';self.e.tick();self.assertEqual(self.k.export()['incidents'][0]['status'],'executing')
    def test_restart_reconciles_durable_operation(self):
        self.start();e=Engine(self.k,self.cfg);e.tick();self.assertEqual(self.remote.calls,1);self.assertEqual(self.k.export()['incidents'][0]['status'],'verified')
    def test_unknown_target_response_is_visible(self):
        original=self.remote.request
        def request(path,data=None):
            value=original(path,data)
            if path.startswith('/sample/'):value['target']='other'
            return value
        self.remote.request=request;self.e.tick();self.assertEqual(self.e.snapshot()['observations']['target']['cause'],'unknown');self.assertEqual(self.remote.calls,0)
    def test_operator_policy_projection_never_exports_transport_or_signing_key(self):
        snapshot=self.e.snapshot()
        self.assertEqual(set(snapshot['policies']['target']),{'baseline','expanded','node','mode'})
        import json
        encoded=json.dumps(snapshot)
        self.assertNotIn('kkkkkkkk',encoded)
        self.assertNotIn('client',encoded)

if __name__=='__main__':unittest.main()
