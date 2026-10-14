"""Measured workflow exercise on app-1. Run only on the healer in the lab.

Preserves existing Knowledge. Pauses the legacy loop during the demonstration.
All faults are configuration drift; it never stops, destroys or reboots a VM.
Uses the production operator database so the evidence survives activation.
"""
import os
import sys
import time
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapek.cloudstack import CloudStack
from mapek.educloud import EduCloudWorld, load_lab
from mapek.loop import Healer
from mapek.operator import Operator


def main():
    state = Path.home()/'projects/selfheal/state'
    pause = state/'paused'
    if pause.exists() or (state/'operator.db').exists():
        sys.exit('Existing pause or operator database: refusing to overwrite demo state')
    pause.touch()
    lab = load_lab()
    world = EduCloudWorld(CloudStack(project=lab['project_id']), 'app-1', lab,
                          key_path=os.environ['LAB_SSH_KEY'])
    op = Operator(str(state/'operator.db'))
    healer = Healer(world, config='C'); healer.operator = op
    def inject():
        ok, detail = world.inject('config_drift')
        assert ok, detail
        # Deliberate maintenance restart makes all three occurrences comparable.
        # Invalid nginx configuration must reject this restart.
        ok, _, _ = world._probe('sudo systemctl restart nginx')
        assert not ok
        for _ in range(5):
            obs = world.observe(False)
            if not obs['probe_error'] and obs['service_running'] is False:
                return
            time.sleep(2)
        raise RuntimeError('Service state did not settle; refusing to approve uncertain evidence')
    try:
        if not world.health(world.observe(False)):
            raise RuntimeError('Target is not initially healthy')
        inject()
        healer.tick()
        case = op.cases()[0]
        assert case['status'] == 'pending' and not world.observe(False)['config_correct']
        print('1. Pending incident, no automatic repair:', case['id'], flush=True)
        print(case['evidence'], flush=True)
        op.decide(case['id'], True, 'guided-demo', 'Confirmed injected invalid nginx directive; restore reference configuration')
        healer.tick()
        assert op.case(case['id'])['verified'] == 1
        print('2. Approved repair independently verified; candidate created', flush=True)
        inject()
        healer.tick(); case = op.cases()[0]
        # An actual human-style SSH change, rather than an operator action call.
        ok, _, err = world._probe('sudo cp /opt/healer/reference/healer.conf /etc/nginx/conf.d/healer.conf && sudo nginx -t && sudo systemctl reload-or-restart nginx')
        assert ok, err
        assert op.record_human(world, case['id'], ['restore_config'], 'guided-demo', 'Manually copied reference config, checked nginx -t and reloaded nginx over SSH')
        print('3. Human repair captured and independently verified', flush=True)
        procedure = op.procedures()[0]
        op.promote(procedure['id'], 'guided-demo')
        print('4. Two distinct successes reviewed; procedure validated', flush=True)
        # Honour the existing five-tick cooldown at the real service tick pace.
        for _ in range(6):
            healer.tick(); time.sleep(10)
        inject()
        healer.tick()
        case = op.cases()[0]
        assert case['verified'] == 1 and case['procedure_id'] == procedure['id']
        assert world.health(world.observe(False))
        print('5. Third occurrence repaired automatically by validated procedure', flush=True)
        reopened = Operator(str(state/'operator.db'))
        assert reopened.procedures()[0]['status'] == 'validated'
        print('6. Validated procedure persists after reopening database', flush=True)
    finally:
        world.observe(False)
        ok, detail = world.restore_config()
        if not ok: print('CLEANUP FAILED:', detail, flush=True)
        pause.unlink(missing_ok=True)


if __name__ == '__main__': main()
