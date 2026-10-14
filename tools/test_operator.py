"""Meaningful approval/identity/validation tests; no cloud calls."""
import os
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapek.operator import Operator
from mapek.world import SimulatedWorld
from mapek.loop import Healer


class World(SimulatedWorld):
    def __init__(self):
        super().__init__()
        self.name = 'app-1'
        self._vm = {'id': 'vm-1', 'projectid': 'project-1'}
        self.lab = {'project_id': 'project-1', 'lab_instances': ['app-1','app-2'],
                    'service': 'nginx', 'config_path': '/test/config'}

    def restore_config(self):
        result = super().restore_config()
        self.service_running = True  # production effector reload-or-restarts nginx
        return result


class Tests(unittest.TestCase):
    def setUp(self):
        self.world = World(); self.op = Operator(':memory:')
        self.world.inject('config_drift')
        self.world.service_running = True

    def gate(self):
        return self.op.authorize(self.world, ['config_drift'], 'manual_configuration_change',
                                 ['restore_config'], self.world.observe(False))

    def approve(self):
        self.op.decide(self.op.cases()[0]['id'], True, 'tester', 'Compared configuration with reference')

    def success(self):
        self.assertFalse(self.gate()[0]); self.approve(); self.assertTrue(self.gate()[0])
        self.world.restore_config(); self.assertTrue(self.op.finish(self.world, True))

    def test_new_incident_waits_and_deduplicates(self):
        for _ in range(10): self.assertFalse(self.gate()[0])
        self.assertEqual(len(self.op.cases()), 1)

    def test_rejection_does_not_reopen_each_tick(self):
        self.gate(); self.op.decide(1, False, 'tester', 'Need more evidence')
        self.assertFalse(self.gate()[0]); self.assertEqual(len(self.op.cases()), 1)

    def test_identity_change_invalidates_approval(self):
        self.gate(); self.approve(); self.world._vm['id'] = 'replacement'
        self.assertFalse(self.gate()[0])

    def test_changed_evidence_invalidates_approval(self):
        self.gate(); self.approve(); self.world.service_running = False
        self.assertFalse(self.gate()[0])
        self.assertEqual(self.op.case(1)['status'], 'superseded')

    def test_expired_approval(self):
        self.op.clock = lambda: 1; self.gate(); self.approve(); self.op.clock = lambda: 902
        self.assertFalse(self.gate()[0])

    def test_one_success_cannot_promote(self):
        self.success()
        with self.assertRaises(ValueError): self.op.promote(1, 'tester')

    def test_two_successes_then_explicit_promotion(self):
        self.success(); self.world.inject('config_drift'); self.success()
        self.op.promote(1, 'tester'); self.world.inject('config_drift')
        self.assertTrue(self.gate()[0])

    def test_scope_does_not_transfer_to_unapproved_target(self):
        self.success(); self.world.inject('config_drift'); self.success(); self.op.promote(1, 'tester')
        self.world.name = 'app-2'; self.world.inject('config_drift')
        self.assertFalse(self.gate()[0])

    def test_manual_repair_requires_actual_verification(self):
        self.gate()
        self.assertFalse(self.op.record_human(self.world, 1, ['restore_config'], 'tester', 'Claimed fixed'))
        self.assertEqual(self.op.procedures(), [])

    def test_manual_success_is_a_candidate(self):
        self.gate(); self.world.restore_config()
        self.assertTrue(self.op.record_human(self.world, 1, ['restore_config'], 'tester', 'Restored known-good config'))
        self.assertEqual(self.op.procedures()[0]['status'], 'candidate')

    def test_arbitrary_commands_refused(self):
        self.gate()
        with self.assertRaises(ValueError): self.op.record_human(self.world, 1, ['rm -rf /'], 'tester', 'Bad command')

    def test_failed_automatic_verification_revokes(self):
        self.success(); self.world.inject('config_drift'); self.success(); self.op.promote(1, 'tester')
        self.world.inject('config_drift'); self.assertTrue(self.gate()[0])
        self.assertFalse(self.op.finish(self.world, False))
        self.assertEqual(self.op.procedures()[0]['status'], 'revoked')

    def test_missing_ownership_refused(self):
        self.world._vm.pop('projectid')
        with self.assertRaises(ValueError): self.gate()

    def test_loop_really_waits_before_repair(self):
        healer = Healer(self.world, config='C'); healer.operator = self.op
        healer.tick(); self.assertFalse(self.world.observe(False)['config_correct'])
        self.approve(); healer.tick(); self.assertTrue(self.world.observe(False)['config_correct'])

    def test_rejected_resolved_condition_can_have_new_occurrence(self):
        self.gate(); self.op.decide(1, False, 'tester', 'Investigate first')
        self.world.restore_config(); self.op.reconcile(self.world, self.world.observe(False))
        self.world.inject('config_drift'); self.gate()
        self.assertEqual(len(self.op.cases()), 2)

    def test_same_case_cannot_supply_two_validations(self):
        self.gate(); self.world.restore_config()
        self.op.record_human(self.world, 1, ['restore_config'], 'tester', 'Restored config')
        with self.assertRaises(ValueError): self.op.record_human(self.world, 1, ['restore_config'], 'tester', 'Again')
        with self.assertRaises(ValueError): self.op.promote(1, 'tester')

    def test_rotation_repair_cannot_verify_with_only_http_health(self):
        self.world.restore_config()
        self.op.capture(self.world, ['disk_high'], 'disk_full', ['fix_log_rotation'], self.world.observe(False))
        self.assertFalse(self.op.record_human(self.world, 1, ['fix_log_rotation'], 'tester', 'Claimed rotation fixed'))

    def test_stale_symptoms_cannot_trigger_autonomous_procedure(self):
        self.success(); self.world.inject('config_drift'); self.success(); self.op.promote(1, 'tester')
        self.assertFalse(self.gate()[0])

    def test_reference_change_requires_new_approval(self):
        self.world.repair_identity = lambda: {'references': ['original'], 'live_config': 'bad'}
        self.gate(); self.approve()
        self.world.repair_identity = lambda: {'references': ['changed'], 'live_config': 'bad'}
        self.assertFalse(self.gate()[0])

    def test_approved_incident_does_not_bypass_high_risk_gate(self):
        healer = Healer(self.world, config='C'); healer.operator = self.op
        healer.last_observation = self.world.observe(False)
        healer._act(1, ['config_drift'], 'manual_configuration_change', ['rebuild_instance'], 'healed')
        self.approve()
        healer._act(2, ['config_drift'], 'manual_configuration_change', ['rebuild_instance'], 'healed')
        self.assertEqual(self.world.rebuilds, 0)
        self.assertTrue(healer.pending_approval)

    def test_unknown_diagnosis_cannot_be_promoted(self):
        for _ in range(2):
            self.world.inject('config_drift')
            case = self.op.capture(self.world, ['config_drift'], 'unknown', [], self.world.observe(False))
            self.world.restore_config()
            self.assertTrue(self.op.record_human(self.world, case['id'], ['restore_config'], 'tester', 'Restored config; cause uncertain'))
        with self.assertRaises(ValueError): self.op.promote(1, 'tester')

    def test_http_health_is_not_valid_configuration(self):
        self.gate(); self.world.restore_config()
        self.world.configuration_verified = lambda: False
        self.assertFalse(self.op.record_human(self.world, 1, ['restore_config'], 'tester', 'Config still has a syntax error'))

    def test_unknown_advisor_gets_captured_evidence(self):
        class Recorder:
            def request(self, **kwargs): self.requested = kwargs
        healer = Healer(self.world, config='C'); healer.operator = self.op
        recorder = Recorder(); healer.advisor = recorder
        self.op.capture(self.world, ['probe_failed'], 'unknown', [], self.world.observe(False))
        healer._ask_advisor('unknown diagnosis', ['probe_failed'], self.world.observe(False))
        self.assertIn('incident_evidence', recorder.requested['observation'])

    def test_known_credentials_redacted_from_evidence_and_notes(self):
        with patch.dict(os.environ, {'CS_SECRET': 'sensitive-test-value'}):
            self.world.diagnostic_evidence = lambda: {'error': 'sensitive-test-value'}
            self.gate()
            self.op.decide(1, False, 'tester', 'sensitive-test-value')
            case = self.op.case(1)
            self.assertNotIn('sensitive-test-value', case['evidence'])
            self.assertEqual(case['notes'], '[REDACTED]')


if __name__ == '__main__': unittest.main()
