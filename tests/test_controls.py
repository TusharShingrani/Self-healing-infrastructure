import sys,time,unittest,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import test_engine as engine_fixture
from platform_healer.transport import RemoteClient,NoRedirect


class ControlsTests(unittest.TestCase):
    setUp=engine_fixture.EngineTests.setUp
    tearDown=engine_fixture.EngineTests.tearDown
    incident=engine_fixture.EngineTests.incident
    start=engine_fixture.EngineTests.start
    def test_observe_mode_blocks_even_an_approved_case(self):
        self.e.set_mode('target','observe','operator','Observe-only comparison baseline')
        self.start();self.assertEqual(self.remote.calls,0)
    def test_mode_needs_named_operator_and_reason(self):
        with self.assertRaises(ValueError):self.e.set_mode('target','automatic','','')
    def test_invalid_mode_or_target_refused(self):
        for target,mode in (('other','automatic'),('target','arbitrary-shell')):
            with self.assertRaises(ValueError):self.e.set_mode(target,mode,'operator','Reviewed operation')
    def test_mode_is_persisted_and_audited(self):
        self.e.set_mode('target','reviewed','operator','Require explicit approval')
        from platform_healer.engine import Engine
        other=Engine(self.k,self.cfg);self.assertEqual(other.mode('target'),'reviewed');self.assertTrue(self.k.export()['audit'])
    def test_sustained_evidence_is_required_before_proposal(self):
        self.cfg['target']['consecutive']=2;self.e.tick();self.remote.errors+=1;self.e.tick()
        self.assertEqual(self.k.export()['incidents'],[])
        self.remote.errors+=1;self.e.tick();self.assertEqual(len(self.k.export()['incidents']),1)
    def test_multiple_successful_observations_required_for_verification(self):
        self.cfg['target']['verification_samples']=3;self.start()
        self.e.tick();self.assertEqual(self.k.export()['incidents'][0]['status'],'executing')
        self.e.tick();self.assertEqual(self.k.export()['incidents'][0]['status'],'executing')
        self.e.tick();self.assertEqual(self.k.export()['incidents'][0]['status'],'verified')
    def test_duplicate_independent_observation_cannot_qualify_window(self):
        self.cfg['target']['verification_samples']=2;self.start();original=self.remote.request
        def request(path,data=None):
            value=original(path,data)
            if path.startswith('/sample/'):value['metrics']['independent_probe_time']=100
            return value
        self.remote.request=request
        for _ in range(5):self.e.tick()
        self.assertEqual(self.k.export()['incidents'][0]['status'],'executing')
    def test_controller_cooldown_defers_repeat_execution(self):
        self.cfg['target']['cooldown_seconds']=60;self.start();self.e.tick();self.remote.soft=64
        self.start();self.assertEqual(self.remote.calls,1)
    def test_observation_recovery_revokes_unused_approval(self):
        case=self.incident();self.e.approve(case['id'],'operator','Reviewed pending repair')
        self.k.resolve_idle('target');self.assertEqual(self.k.export()['incidents'][0]['status'],'resolved')


    def test_later_success_cannot_count_an_earlier_failed_client_observation(self):
        from test_gateway import evidence
        self.cfg['target'].update(baseline=[40000,40031],expanded=[40000,40255],verification_samples=3)
        original=self.remote.request;client_ok=False;observer_clock=time.time()
        def request(path,data=None):
            nonlocal observer_clock
            value=original(path,data)
            if path.startswith('/sample/'):
                observer_clock+=.01
                repaired=self.remote.soft==256
                value['kind']='gateway_ports'
                value['metrics']=evidence(range=[40000,40255] if repaired else [40000,40031],range_size=256 if repaired else 32,
                    backend_connect_errors=self.remote.errors,gateway_5xx=self.remote.errors,
                    gateway_transaction_ok=repaired,client_transaction_ok=client_ok,
                    independent_probe_time=observer_clock)
            return value
        self.remote.request=request;case=self.start();self.e.tick()
        def status():return next(row['status'] for row in self.k.export()['incidents'] if row['id']==case['id'])
        self.assertEqual(status(),'executing')
        self.assertEqual(self.k.db.execute('SELECT count(*) FROM verification_windows').fetchone()[0],0)
        client_ok=True
        for _ in range(3):self.e.tick()
        self.assertEqual(status(),'verified')


class TLSContractTests(unittest.TestCase):
    def test_plaintext_not_implicitly_allowed(self):
        with self.assertRaises(ValueError):RemoteClient('http://example.invalid')
    def test_mtls_cannot_be_downgraded_even_by_lab_flag(self):
        with self.assertRaises(ValueError):RemoteClient('http://example.invalid',True,'/missing')
    def test_missing_private_ca_fails_closed(self):
        with self.assertRaises(OSError):RemoteClient('https://example.invalid',tls_directory='/definitely-missing-pki')
    def test_redirect_to_another_destination_is_refused(self):
        request=urllib.request.Request('https://agent.invalid/execute')
        with self.assertRaises(urllib.error.HTTPError):NoRedirect().redirect_request(request,None,302,'redirect',{},'http://outside.invalid/')


if __name__=='__main__':unittest.main()
