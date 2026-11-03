import http.client,importlib.util,json,sys,threading,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from platform_healer.demo_service import TARGET,make_server,validate_result
from platform_healer.model import digest
from platform_healer.gateway_observer import check
spec=importlib.util.spec_from_file_location('video_demo',ROOT/'experiments/video_demo.py');video=importlib.util.module_from_spec(spec);spec.loader.exec_module(video)

class ProbeContractTests(unittest.TestCase):
    def result(self,**changes):return dict({'target':TARGET,'time':100,'success':True,'status':200,'latency_seconds':.02},**changes)
    def test_stale_wrong_target_and_false_success_refused(self):
        for value in (self.result(time=80),self.result(target='http://other'),self.result(status=503),self.result(latency_seconds=float('nan'))):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_result(value,100)
    def test_real_http_failure_remains_a_known_failure(self):
        self.assertEqual(validate_result(self.result(success=False,status=503),100)['status'],503)
    def test_no_response_is_not_fabricated_as_http_503(self):
        self.assertEqual(validate_result(self.result(success=False,status=0),100)['status'],0)
    def test_observer_checks_body_and_status_on_actual_production_method(self):
        response=Mock();response.status=200;response.read.return_value=b'wrong response'
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.return_value=response
        with patch('platform_healer.gateway_observer.fixed_opener',return_value=opener):
            value=check()
        self.assertFalse(value['success']);self.assertEqual(value['status'],200)
        self.assertIn('/transaction?nonce=',opener.open.call_args.args[0])

class DemoHTTPTests(unittest.TestCase):
    def setUp(self):
        self.probe=Mock();self.probe.check.return_value={'time':time.time(),'success':False,'status':503,'latency_seconds':.1}
        self.server=make_server(self.probe,0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join(2)
    def request(self,path,host=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        conn.request('GET',path,headers={} if host is None else {'Host':host})
        response=conn.getresponse();status=response.status;body=response.read();conn.close();return status,body
    def test_failure_display_uses_actual_probe_outcome(self):
        status,body=self.request('/api/check');self.assertEqual(status,200);self.assertEqual(json.loads(body)['status'],503);self.assertFalse(json.loads(body)['success']);self.probe.check.assert_called_once()
    def test_monitoring_outage_is_not_a_gateway_failure(self):
        self.probe.check.side_effect=OSError('private detail');status,body=self.request('/api/check');self.assertEqual(status,502);self.assertNotIn(b'private detail',body);self.assertNotIn(b'success',body)
    def test_page_is_read_only_and_unknown_routes_are_refused(self):
        self.assertEqual(self.request('/')[0],200);self.assertEqual(self.request('/api/approve')[0],404);self.probe.check.assert_not_called()
    def test_dns_rebinding_host_is_refused(self):self.assertEqual(self.request('/api/check','evil.example:8086')[0],403);self.probe.check.assert_not_called()
    def test_two_viewers_work_and_additional_concurrency_is_bounded(self):
        from concurrent.futures import ThreadPoolExecutor
        release=threading.Event();entered=threading.Event();lock=threading.Lock();count=[0]
        def blocking_check():
            with lock:
                count[0]+=1
                if count[0]==2:entered.set()
            release.wait(3)
            return {'time':time.time(),'success':True,'status':200,'latency_seconds':.1}
        self.probe.check.side_effect=blocking_check
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(self.request,'/api/check');second=pool.submit(self.request,'/api/check')
            try:
                self.assertTrue(entered.wait(2));self.assertEqual(self.request('/api/check')[0],429)
            finally:release.set()
            self.assertEqual(first.result()[0],200);self.assertEqual(second.result()[0],200)

class VideoAdmissionTests(unittest.TestCase):
    def snapshot(self):
        sample={'target':'gateway-ports','kind':'gateway_ports','identity':'owned','time':time.time(),'error':'','metrics':{'range':[40000,40031],'active_connections':0,'allocation_probe_errno':0,'reserved_conflict':False,'headroom_safe':True,'client_transaction_ok':True,'gateway_transaction_ok':True,'upstream_healthy':True}}
        return {'observations':{'gateway-ports':{'sample':sample}},'procedures':[],'incidents':[],'policies':{'gateway-ports':{'mode':'reviewed'}}}
    def test_unqualified_automatic_run_cannot_inject_load_or_change_mode(self):
        api=Mock(return_value=self.snapshot());admin=Mock()
        with self.assertRaisesRegex(ValueError,'not qualified'):video.run(api,admin,'automatic','tester')
        admin.run.assert_not_called();self.assertEqual(api.call_args_list,[(('/api/status',),)])
    def test_validated_procedure_from_other_identity_is_refused(self):
        s=self.snapshot();s['procedures']=[{'scope':'other','cause':'gateway_outbound_port_exhaustion','action':'expand_port_range','status':'validated'}]
        with self.assertRaises(ValueError):video.require_automatic(s,s['observations']['gateway-ports']['sample'])
    def test_candidate_cannot_supply_permission(self):
        s=self.snapshot();sample=s['observations']['gateway-ports']['sample'];scope=digest({'identity':'owned','kind':'gateway_ports','target':'gateway-ports','protocol':1})
        p={'scope':scope,'cause':'gateway_outbound_port_exhaustion','action':'expand_port_range','status':'candidate'};s['procedures']=[p]
        with self.assertRaises(ValueError):video.require_automatic(s,sample)
        p['status']='validated';video.require_automatic(s,sample)
    def test_unhealthy_baseline_cannot_inject_load(self):
        s=self.snapshot();s['observations']['gateway-ports']['sample']['metrics']['client_transaction_ok']=False
        api=Mock(return_value=s);admin=Mock()
        with self.assertRaises(ValueError):video.run(api,admin,'reviewed','tester')
        admin.run.assert_not_called()

if __name__=='__main__':unittest.main()
