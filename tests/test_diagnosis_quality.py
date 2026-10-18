import json
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from diagnosis_quality import make_cases,classify_packet
from summarize_diagnosis_quality import summarise,report_hash,FLAGS
from platform_healer.model import digest


class DiagnosisQualityTests(unittest.TestCase):
    def test_predefined_cases_have_expected_checklist_labels(self):
        cases=make_cases()
        self.assertEqual(len(cases),7)
        for case in cases:
            with self.subTest(case=case['id']):
                self.assertEqual(classify_packet(case['packet']),case['expected'])

    def test_provider_packets_do_not_include_ground_truth_or_target_identity(self):
        for case in make_cases():
            raw=json.dumps(case['packet'])
            self.assertTrue({'id','expected','origin'}.isdisjoint(case['packet']))
            if case['expected'].startswith('gateway_'):
                self.assertNotIn(case['expected'],raw)
            self.assertNotIn('replay-target',raw)
            self.assertNotIn('expected',raw)

    def test_stale_packet_is_unknown_even_with_strong_historical_signature(self):
        case=next(c for c in make_cases() if c['id']=='stale_evidence')
        self.assertEqual(classify_packet(case['packet']),'unknown')
        self.assertEqual(case['packet']['metrics']['allocation_probe_errno'],99)

    def test_historical_counters_do_not_override_current_recovery(self):
        case=next(c for c in make_cases() if c['id']=='recovered_old_counters')
        self.assertGreater(case['packet']['current']['metrics']['gateway_5xx'],0)
        self.assertEqual(classify_packet(case['packet']),'healthy')

    def test_export_refuses_unreviewed_report_variation(self):
        cases=make_cases();rows=[];grades={}
        for case in cases:
            report={'summary':'reviewed response'}
            rows.append({'case':case['id'],'available':True,'input_digest':digest(case['packet']),
                'baseline':case['expected'],'latency_seconds':1,
                'result':{'evidence_digest':digest(case['packet']),'report':report}})
            grades[case['id']]=dict({flag:False for flag in FLAGS},reviewed_report_sha256=report_hash(report),reason='Test review')
        study={'cases':cases,'model':'test','runs':rows,'repetitions':1,'rubric_sha256':'protocol'}
        review={'rubric_sha256':'protocol','cases':grades}
        self.assertEqual(summarise(study,review)['valid_reports'],7)
        altered=copy.deepcopy(study);altered['runs'][0]['result']['report']['summary']='unreviewed variation'
        with self.assertRaisesRegex(ValueError,'Unreviewed'):summarise(altered,review)

    def test_export_refuses_wrong_evidence_or_protocol(self):
        with self.assertRaisesRegex(ValueError,'protocol'):
            summarise({'rubric_sha256':'one'},{'rubric_sha256':'two'})


if __name__=='__main__':unittest.main()
