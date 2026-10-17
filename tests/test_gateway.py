import sys,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from platform_healer.model import Sample
from platform_healer.analyse import analyse
from platform_healer.plugins.gateway import admission,reserved_overlap,Gateway

SPEC={'id':'gateway-ports','namespace':'platform-healer-gateway','baseline':[40000,40031],'expanded':[40000,40255],
      'minimum_memory_bytes':268435456,'minimum_memory_ratio':.15}


def evidence(**changes):
    metrics=dict(used_ports=32,range_size=32,backend_connect_errors=5,gateway_5xx=5,allocation_probe_errno=99,
        upstream_healthy=True,gateway_transaction_ok=False,client_transaction_ok=False,headroom_safe=True,
        reserved_conflict=False,memory_available_bytes=1024**3,memory_available_ratio=.5,active_connections=32)
    metrics.update(changes);return metrics


class GatewayAnalysisTests(unittest.TestCase):
    def diagnose(self,**changes):
        current=Sample('gateway-ports','gateway_ports','same',100,evidence(**changes))
        previous=Sample('gateway-ports','gateway_ports','same',99,evidence(backend_connect_errors=4,gateway_5xx=4))
        return analyse(current,previous,100)
    def test_correlated_real_gateway_failure_has_bounded_plan(self):self.assertEqual(self.diagnose().action,'expand_port_range')
    def test_backend_outage_is_not_port_exhaustion(self):
        result=self.diagnose(upstream_healthy=False);self.assertEqual(result.cause,'gateway_dependency_unavailable');self.assertIsNone(result.action)
    def test_generic_haproxy_errors_without_errno_do_not_authorise(self):self.assertIsNone(self.diagnose(allocation_probe_errno=111).action)
    def test_healthy_upstream_without_client_failure_is_insufficient(self):self.assertIsNone(self.diagnose(gateway_transaction_ok=True,client_transaction_ok=True).action)
    def test_local_failure_without_independent_client_failure_needs_investigation(self):self.assertIsNone(self.diagnose(client_transaction_ok=True).action)
    def test_memory_pressure_blocks_plan(self):self.assertEqual(self.diagnose(headroom_safe=False).cause,'gateway_unsafe_headroom')
    def test_reserved_ports_block_plan(self):self.assertEqual(self.diagnose(reserved_conflict=True).cause,'gateway_reserved_port_conflict')
    def test_counter_reset_is_unknown(self):self.assertEqual(self.diagnose(backend_connect_errors=0).cause,'unknown')
    def test_missing_client_measurement_is_unknown(self):self.assertEqual(self.diagnose(client_transaction_ok=None).cause,'unknown')
    def test_missing_previous_sample_cannot_authorise(self):self.assertIsNone(analyse(Sample('g','gateway_ports','same',100,evidence()),now=100).action)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        self.tls=patch("platform_healer.plugins.gateway.client_context",return_value=None);self.tls.start();self.addCleanup(self.tls.stop)
    def test_safe_bounded_load_admitted(self):admission(evidence(),SPEC)
    def test_low_absolute_memory_refused(self):
        with self.assertRaises(ValueError):admission(evidence(memory_available_bytes=1),SPEC)
    def test_low_relative_memory_refused(self):
        with self.assertRaises(ValueError):admission(evidence(memory_available_ratio=.01),SPEC)
    def test_unknown_memory_refused(self):
        value=evidence();del value['memory_available_bytes']
        with self.assertRaises(ValueError):admission(value,SPEC)
    def test_reserved_overlap_refused(self):
        with self.assertRaises(ValueError):admission(evidence(reserved_conflict=True),SPEC)
    def test_backend_down_refused(self):
        with self.assertRaises(ValueError):admission(evidence(upstream_healthy=False),SPEC)
    def test_unqualified_load_refused(self):
        with self.assertRaises(ValueError):admission(evidence(active_connections=129),SPEC)
    def test_reserved_range_parsing(self):
        self.assertTrue(reserved_overlap('1,40030-40040,50000',[40000,40255]));self.assertFalse(reserved_overlap('1,50000-51000',[40000,40255]))
    def test_arbitrary_range_refused(self):
        gateway=Gateway(SPEC)
        with self.assertRaises(ValueError):gateway.validate([1000,65535])
    def test_missing_observer_refuses_even_when_memory_is_safe(self):
        gateway=Gateway(SPEC);gateway.sample=lambda:Sample('gateway-ports','gateway_ports','same',time.time(),evidence(),error='Observer stale')
        with self.assertRaises(ValueError):gateway.validate(SPEC['expanded'])

if __name__=='__main__':unittest.main()
