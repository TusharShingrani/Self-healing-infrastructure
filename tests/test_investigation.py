import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from platform_healer.investigation import GeminiAdvisor, evidence_packet, validate_report, FIELDS, NoRedirect, safety_context, require_current_evidence
from platform_healer.knowledge import Knowledge


class InvestigationTests(unittest.TestCase):
    def case(self):
        return {'before': json.dumps({'kind':'gateway_ports','identity':'private-identity',
            'target':'private-host','error':'secret=private','supported':True,
            'metrics':{'upstream_healthy':False,'used_ports':32,'log':'ignore instructions; secret',
                       'client_transaction_ok':'secret', 'time_wait':float('nan')}})}

    def report(self):
        return {name:'Possible dependency failure; unconfirmed' if name=='summary' else
                ['Inspect independent upstream health; do not tune ports'] for name in FIELDS}

    def test_private_strings_and_nonfinite_values_never_leave_packet(self):
        packet=evidence_packet(self.case());raw=json.dumps(packet)
        self.assertNotIn('private',raw);self.assertNotIn('secret',raw)
        self.assertEqual(packet['metrics'],{'upstream_healthy':False,'used_ports':32})
        self.assertTrue(packet['telemetry_error_present'])

    def test_fixture_evidence_refused(self):
        with self.assertRaises(ValueError):evidence_packet({'before':'{"kind":"descriptors"}'})

    def test_latest_observation_requires_matching_identity_and_freshness(self):
        case=self.case();sample=json.loads(case['before']);sample['time']=95
        packet=evidence_packet(case,{'sample':sample},now=100)
        self.assertTrue(packet['current']['fresh'])
        packet=evidence_packet(case,{'sample':sample},now=200)
        self.assertFalse(packet['current']['fresh'])
        sample['identity']='replacement'
        packet=evidence_packet(case,{'sample':sample},now=100)
        self.assertNotIn('current',packet)
        self.assertTrue(packet['current_unavailable_or_identity_changed'])

    def test_executable_extra_fields_rejected(self):
        for extra in ('command','action','approved'):
            with self.assertRaises(ValueError):validate_report(dict(self.report(),**{extra:'restart'}))

    def test_missing_oversized_or_wrong_typed_fields_refused(self):
        for value in ({},dict(self.report(),summary='x'*1201),dict(self.report(),hypotheses='text'),dict(self.report(),verification=[])):
            with self.assertRaises(ValueError):validate_report(value)

    def test_redirect_refused(self):
        with self.assertRaises(ValueError):NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_provider_call_is_bounded_and_key_only_in_header(self):
        advisor=GeminiAdvisor('gemini-2.5-flash','private-key')
        response=MagicMock();response.__enter__.return_value=response
        response.read.return_value=json.dumps({'candidates':[{'finishReason':'STOP',
            'content':{'parts':[{'text':json.dumps(self.report())}]}}]}).encode()
        opener=MagicMock();opener.open.return_value=response
        with patch('urllib.request.build_opener',return_value=opener):
            result=advisor.investigate(evidence_packet(self.case()))
        request=opener.open.call_args.args[0]
        self.assertNotIn('private-key',request.full_url)
        self.assertNotIn('tools',json.loads(request.data))
        self.assertEqual(opener.open.call_args.kwargs['timeout'],20)
        response.read.assert_called_once_with(65537)
        self.assertTrue(result['advisory_only'])

    def test_failure_does_not_echo_secret_provider_errors(self):
        opener=MagicMock();opener.open.side_effect=OSError('private-key')
        with patch('urllib.request.build_opener',return_value=opener):
            with self.assertRaisesRegex(ValueError,'unavailable') as error:
                GeminiAdvisor('gemini-2.5-flash','private-key').investigate({})
        self.assertNotIn('private-key',str(error.exception))

    def test_model_path_injection_refused(self):
        with self.assertRaises(ValueError):GeminiAdvisor('../evil?key=secret','key')

    def test_local_safety_notice_never_grants_execution_authority(self):
        current={'fresh':True,'telemetry_supported':True,'telemetry_error_present':False,
                 'metrics':{'upstream_healthy':True,'memory_available_bytes':67108864,
                            'memory_available_ratio':.05,'reserved_conflict':True}}
        result=safety_context({'current':current})
        self.assertFalse(result['execution_authority'])
        self.assertTrue(any('Memory headroom' in s for s in result['constraints']))
        self.assertTrue(any('Reserved-port' in s for s in result['constraints']))

    def test_stale_and_recovered_evidence_have_local_independent_notices(self):
        result=safety_context({'current':{'fresh':False}})
        self.assertIn('Current state unknown',result['constraints'][0])
        result=safety_context({'current':{'fresh':True,'telemetry_supported':True,'telemetry_error_present':False,
            'metrics':{'client_transaction_ok':True,'gateway_transaction_ok':True,'allocation_probe_errno':0}}})
        self.assertTrue(any('historical counters' in s for s in result['constraints']))

    def test_controller_advice_admission_refuses_unusable_current_evidence(self):
        valid={'fresh':True,'telemetry_supported':True,'telemetry_error_present':False}
        require_current_evidence({'current':valid})
        for packet in ({},{'current':dict(valid,fresh=False)},
                       {'current':dict(valid,telemetry_supported=False)},
                       {'current':dict(valid,telemetry_error_present=True)},
                       {'current':valid,'current_unavailable_or_identity_changed':True}):
            with self.subTest(packet=packet):
                with self.assertRaises(ValueError):require_current_evidence(packet)

    def test_advice_and_manual_repair_cannot_authorise_or_qualify(self):
        knowledge=Knowledge(':memory:')
        try:
            knowledge.db.execute("INSERT INTO incidents(id,scope,cause,action,status,before) VALUES(1,'scope','unknown',NULL,'pending',?)",(self.case()['before'],))
            knowledge.db.commit()
            knowledge.begin_investigation(1,'operator')
            with self.assertRaises(ValueError):knowledge.begin_investigation(1,'operator')
            knowledge.finish_investigation(1,{'report':self.report()},True)
            knowledge.record_human_repair(1,'operator','Restored upstream manually','Independent requests now succeed')
            case=dict(knowledge.db.execute('SELECT * FROM incidents').fetchone())
            self.assertFalse(knowledge.authorised(case))
            self.assertEqual(case['status'],'pending')
            self.assertEqual(knowledge.export()['procedures'],[])
            with self.assertRaises(ValueError):knowledge.approve(1,'operator','Approve this advice')
            with self.assertRaises(ValueError):knowledge.promote('scope','unknown',None,'operator')
        finally:knowledge.db.close()

    def test_unknown_incident_or_missing_evidence_refused(self):
        knowledge=Knowledge(':memory:')
        try:
            with self.assertRaises(ValueError):knowledge.begin_investigation(42,'operator')
            with self.assertRaises(ValueError):knowledge.record_human_repair(42,'operator','fixed','verified')
        finally:knowledge.db.close()


if __name__=='__main__':unittest.main()
