"""Measurement rules exclude planned cancellation and isolated lucky probes."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from restart_comparison import recovery,interruptions

class RestartMeasurementsTests(unittest.TestCase):
    def test_one_lucky_success_is_not_stable_recovery(self):
        self.assertIsNone(recovery([{'time':i,'success':value} for i,value in enumerate([False,True,False,False])],0))
    def test_requires_three_consecutive_successes_after_action(self):
        rows=[{'time':i,'success':value} for i,value in enumerate([True,True,True,False,True,True,True])]
        self.assertEqual(recovery(rows,3),4)
    def test_planned_shutdown_and_new_requests_are_not_interrupted_old_requests(self):
        events=[{'sent':1,'finished':4,'result':'connection_error'},
                {'sent':1,'finished':4,'result':'cancelled'},
                {'sent':3,'finished':4,'result':'connection_error'},
                {'sent':1,'finished':12,'result':'connection_error'},
                {'sent':None,'finished':4,'result':'connection_error'},
                {'sent':1,'finished':4,'result':'http_error'}]
        self.assertEqual(interruptions(events,2,10),1)

if __name__=='__main__':unittest.main()
