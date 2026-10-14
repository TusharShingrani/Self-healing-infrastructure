"""Exercise the production transaction and its failure-path measurement."""
import concurrent.futures
import importlib.util
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('transaction',Path(__file__).parent/'stack-host/transaction.py')
tx=importlib.util.module_from_spec(spec);spec.loader.exec_module(tx)


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.spool=str(Path(self.temp.name,'checkpoint'))
        self.path=patch.object(tx,'SPOOL',self.spool);self.path.start();self.addCleanup(self.path.stop)
    def test_wrong_dns_does_not_connect_to_wrong_cache(self):
        with patch.object(tx,'resolve',return_value='10.1.1.62'),patch.object(tx,'redis_command') as redis:
            result=tx.transaction()
        self.assertFalse(result['healthy']);self.assertIsNone(result['checks']['cache_write']);redis.assert_not_called()
    def test_dns_timeout_is_not_healthy(self):
        with patch.object(tx,'resolve',side_effect=TimeoutError('timed out')):
            result=tx.transaction()
        self.assertFalse(result['checks']['dns_record']);self.assertFalse(result['healthy'])
    def test_cache_oom_keeps_cause_evidence(self):
        with patch.object(tx,'resolve',return_value=tx.EXPECTED),patch.object(tx,'redis_command',side_effect=ValueError('-OOM budget exceeded')):
            result=tx.transaction()
        self.assertFalse(result['checks']['cache_write']);self.assertIn('OOM',result['evidence']['cache_write'])
    def test_checkpoint_failure_does_not_blame_cache(self):
        with patch.object(tx,'resolve',return_value=tx.EXPECTED),patch.object(tx,'redis_command',return_value='$2\r\nok'),patch.object(tx,'open',create=True,side_effect=PermissionError('checkpoint denied')):
            result=tx.transaction()
        self.assertFalse(result['checks']['spool_write']);self.assertTrue(result['checks']['cache_write']);self.assertIn('denied',result['evidence']['spool_write'])
    def test_concurrent_readback_survives_slow_truncate(self):
        original_open=open
        def slow_open(path,mode='r'):
            handle=original_open(path,mode)
            if mode=='w':time.sleep(.002)  # Expose the previous truncate/read race.
            return handle
        with patch.object(tx,'resolve',return_value=tx.EXPECTED),patch.object(tx,'redis_command',return_value='$2\r\nok'),patch.object(tx,'open',create=True,side_effect=slow_open):
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                results=list(pool.map(lambda _:tx.transaction(),range(120)))
        self.assertTrue(all(r['healthy'] for r in results))


if __name__=='__main__':unittest.main(verbosity=2)
