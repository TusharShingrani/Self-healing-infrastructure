"""Show the production advisor and approval flow using a simulated target.

python3 tools/demo_advice.py
python3 tools/demo_advice.py --decision approve
python3 tools/demo_advice.py --real

--real calls the configured Gemini provider, but all repair actions still target
the simulation. Never presents a simulated repair as a live cloud repair.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapek.advisor import Advisor, default_provider
from mapek.loop import Healer
from mapek.world import SimulatedWorld


class ProbeFailure(SimulatedWorld):
    def __init__(self):
        super().__init__()
        self.stuck = True
        self.repairs = 0

    def observe(self, sample=True):
        obs = super().observe(sample)
        if self.stuck:
            obs['probe_error'] = 'demonstration: simulated metrics agent stuck'
        return obs

    def health(self, obs):
        return super().health(obs) and not obs.get('probe_error')

    def restart_service(self):
        self.stuck = False
        self.repairs += 1
        return super().restart_service()


class DemoProvider:
    model = 'demo-fake-provider'

    def __init__(self, risky=False):
        self.risky = risky

    def ask(self, system, prompt):
        return {'cause': 'metrics_agent_stuck', 'actions': ['rebuild_instance' if self.risky else 'restart_service'],
                'risk': 'low', 'explanation': ('Intentionally asks for a rebuild to demonstrate the gate; not a recommended repair.' if self.risky else 'A simulated agent is stuck; restart clears it.'),
                'human_checks': ['Check probe_error disappears after the repair.']}, self.model


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--real', action='store_true')
    ap.add_argument('--risky', action='store_true', help='fake-provider demonstration of the separate high-risk gate')
    ap.add_argument('--decision', choices=['approve', 'reject'])
    args = ap.parse_args()
    if args.real and args.risky:
        sys.exit('--risky is only supported with the fake provider.')
    provider = default_provider() if args.real else DemoProvider(args.risky)
    if provider is None:
        sys.exit('No Gemini provider configured. Export GEMINI_API_KEY in memory first.')
    print('TARGET: SIMULATION. Cloud API and real VM repairs are never called.')
    print('PROVIDER:', 'LIVE GEMINI REQUEST' if args.real else 'FAKE PROVIDER; no LLM request')
    world = ProbeFailure()
    healer = Healer(world, config='C')
    healer.advisor = Advisor(healer.knowledge, provider=provider, run_async=False)
    healer.tick()
    advice = healer.knowledge.advice()[0]
    print('Before approval: status=%s, repairs=%s' % (advice['status'], world.repairs))
    print(json.dumps({k: advice[k] for k in ['id','model','cause','actions','risk','explanation','human_checks']}, indent=2))
    if advice['status'] != 'pending':
        sys.exit('No pending advice. Inspect the provider outcome; nothing was approved.')
    decision = args.decision or input('Type approve or reject: ').strip().lower()
    if decision not in ('approve', 'reject'):
        sys.exit('No decision made; advice remains pending.')
    if decision == 'approve' and not json.loads(advice['actions']):
        sys.exit('The model proposed no catalogue action. Nothing can be approved for execution.')
    healer.knowledge.decide_advice(advice['id'], approve=decision == 'approve', who='demo-operator')
    healer.tick()
    print('After decision: status=%s, repairs=%s, healthy=%s' % (
        healer.knowledge.advice()[0]['status'], world.repairs,
        world.health(world.observe(sample=False))))
    print('High-risk proposals still require their separate gate:', healer.pending_approval)
    print('Event:', healer.events[-1].kind, healer.events[-1].detail)


if __name__ == '__main__':
    main()
