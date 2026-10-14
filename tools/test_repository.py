"""Regression checks for issues reproduced during the whole-repository audit."""
import io
import json
import tempfile
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mapek.educloud import HostRegistry, HostIdentityChanged
from mapek.cloudstack import CloudStack, CloudStackError
from mapek.infrastructure import InfrastructureWorld
from mapek.stages import Monitor
from test_operator import World
from mapek.operator import Operator


class Response(io.BytesIO):
    code = 200


class Tests(unittest.TestCase):
    def test_stale_registry_writer_preserves_other_process(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory)/'hosts.json')
            a, b = HostRegistry(path), HostRegistry(path)
            a.remember('ip-1', 'vm-1'); b.remember('ip-2', 'vm-2')
            self.assertEqual(a.known_instance('ip-2'), 'vm-2')
            self.assertEqual(b.known_instance('ip-1'), 'vm-1')

    def test_corrupt_registry_does_not_reset_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'hosts.json'; path.write_text('[]')
            with self.assertRaises(HostIdentityChanged): HostRegistry(str(path))

    def test_missing_instance_identity_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(HostIdentityChanged):
                HostRegistry(str(Path(directory)/'hosts.json')).remember('ip', None)

    def test_http_200_api_error_is_failure(self):
        client = CloudStack('https://example.invalid/api', 'test-key', 'test-secret')
        for payload in ({'errorresponse':{'errorcode':431}},
                        {'destroyvirtualmachineresponse':{'errorcode':530}}, [], {}):
            with self.subTest(payload=payload), patch('urllib.request.urlopen', return_value=Response(json.dumps(payload).encode())):
                with self.assertRaises(CloudStackError): client.call('destroyVirtualMachine', id='lab')

    def test_normal_empty_list_response_is_valid(self):
        client = CloudStack('https://example.invalid/api', 'test-key', 'test-secret')
        with patch('urllib.request.urlopen',return_value=Response(b'{"listvirtualmachinesresponse":{}}')):
            self.assertEqual(client.instances(), [])

    def observe(self, payload, cache_reply=(False, '', 'NOAUTH')):
        def command(node, text):
            return cache_reply if 'CONFIG GET' in text else (True, 'active', '')
        world = SimpleNamespace(tick_count=1, ownership=lambda:None, command=command, latest={})
        with patch('urllib.request.urlopen',return_value=Response(json.dumps(payload).encode())):
            return InfrastructureWorld.observe(world,False)

    def test_unreadable_independent_budget_enters_investigation(self):
        obs = self.observe({'healthy':True,'checks':dict.fromkeys(('dns_record','cache_write','spool_write'),True)})
        self.assertIn('probe_failed',Monitor().symptoms(obs))
        self.assertFalse(InfrastructureWorld.health(None,obs))

    def test_malformed_transaction_payload_is_recorded(self):
        for payload in ([], {'checks':[]}, {'checks':{'dns_record':'true'}}):
            with self.subTest(payload=payload):
                self.assertIn('probe_failed',Monitor().symptoms(self.observe(payload)))

    def test_extra_symptom_cannot_reuse_approved_repair(self):
        world = World(); op = Operator(':memory:')
        world.inject('config_drift'); world.service_running=True
        obs=world.observe(False)
        case=op.capture(world,['config_drift'],'manual_configuration_change',['restore_config'],obs)
        op.decide(case['id'],True,'tester','reviewed')
        world.service_running=False
        self.assertFalse(op.authorize(world,['config_drift'],'manual_configuration_change',['restore_config'],obs)[0])
        self.assertEqual(op.case(case['id'])['status'],'superseded')

    def test_nginx_metrics_does_not_wait_for_tick_lock(self):
        from healer_service import Service
        service=SimpleNamespace(metrics_snapshot='completed tick\n')
        self.assertEqual(Service.metrics(service),'completed tick\n')

    def test_dependency_http_responds_during_slow_tick(self):
        script = '''
import socket, time
from types import SimpleNamespace
import infrastructure_service as service
original = service.ThreadingHTTPServer
def server(address, handler):
    result = original(('127.0.0.1', 0), handler)
    global port
    port = result.server_address[1]
    return result
def tick():
    print(port, flush=True)
    time.sleep(5)
def forbid(): raise RuntimeError('HTTP must not query mutable operator state')
service.ThreadingHTTPServer = server
service.build = lambda: (SimpleNamespace(), SimpleNamespace(cases=forbid, procedures=forbid),
    SimpleNamespace(knowledge=SimpleNamespace(expire_advice=lambda:None), tick=tick))
service.main()
'''
        child=subprocess.Popen([sys.executable,'-c',script],cwd=Path(__file__).parent,
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            port=int(child.stdout.readline())
            import urllib.request
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/metrics',timeout=1) as response:
                self.assertIn(b'snapshot_ready 0',response.read())
        finally:
            child.terminate()
            try: child.wait(timeout=1)
            except subprocess.TimeoutExpired: child.kill();child.wait()
            child.stdout.close(); child.stderr.close()

    def test_unhealthy_without_named_symptom_requires_investigation(self):
        from mapek.loop import Healer
        world=World(); world.health=lambda observation:False
        world.observe=lambda sample=True:{'tick':world.tick_count,'reachable':True}
        healer=Healer(world)
        healer.tick()
        self.assertEqual(healer.last_symptoms,['probe_failed'])
        self.assertEqual(healer.events[-1].kind,'escalated')

    def test_clear_logs_refuses_before_any_mutation(self):
        from mapek.educloud import EduCloudWorld
        effects=[]
        def refuse(): raise RuntimeError('unbounded mount')
        world=SimpleNamespace(assert_bounded_log_mount=refuse,_guest=lambda *args:effects.append(args))
        with self.assertRaises(RuntimeError): EduCloudWorld.clear_logs(world)
        self.assertEqual(effects,[])

    def test_cloud_error_redacts_signed_url_and_keys(self):
        client=CloudStack('https://example.invalid/api','test-key','test-secret')
        result=client._safe_error('test-key test-secret https://example.invalid/api?apikey=test-key&signature=abc')
        self.assertNotIn('test-key',result);self.assertNotIn('test-secret',result)
        self.assertNotIn('signature',result)

    def test_infrastructure_advisor_uses_correct_context(self):
        from mapek.advisor import Advisor
        from mapek.knowledge import Knowledge
        class Provider:
            def ask(self,system,prompt):
                self.system=system;self.prompt=prompt
                return {'cause':'unknown','actions':[],'explanation':'investigate','risk':'low','human_checks':['check DNS']},'fake'
        provider=Provider();advisor=Advisor(Knowledge(),provider,run_async=False)
        advisor.request('app-1','unknown',['probe_failed'],{'monitor_source':'direct-dependency-transaction'})
        self.assertIn('DNS :1053',provider.system)
        self.assertIn('These are not nginx checks',provider.system)


if __name__=='__main__': unittest.main(verbosity=2)
