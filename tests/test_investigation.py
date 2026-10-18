import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from platform_healer.investigation import GeminiAdvisor, evidence_packet, validate_report, FIELDS, NoRedirect
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
