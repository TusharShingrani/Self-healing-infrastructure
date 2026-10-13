"""Knowledge and the human-in-the-loop advisor, against the simulation.

No API calls: a fake client stands in for Claude. These tests pin down the
safety properties of advice, which matter more than its quality:

  - advice is stored as pending and never runs by itself
  - only approved advice is used, and only with catalogue actions
  - approved advice still passes the high-risk approval gate
  - a missing SDK, missing credentials or a failing call never stalls the loop

Run:  python3 tools/test_learning.py
"""

import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapek.advisor import Advisor                                # noqa: E402
from mapek.loop import Healer                                    # noqa: E402
from mapek.world import SimulatedWorld                           # noqa: E402

passed = failed = 0


def check(name, condition, note=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {note}")


class StuckAgentWorld(SimulatedWorld):
    """A failure no rule knows: the instance reports a probe error until the
    service is restarted. Symptoms are only ["probe_failed"]."""

    def __init__(self):
        super().__init__()
        self.agent_stuck = True
        self.restarts = 0

    def observe(self, sample=True):
        obs = super().observe(sample)
        if self.agent_stuck:
            obs["probe_error"] = "metrics agent stuck"
        return obs

    def health(self, observation):
        return super().health(observation) and not observation.get("probe_error")

    def restart_service(self):
        self.restarts += 1
        self.agent_stuck = False
        return super().restart_service()


class FakeClient:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, 0
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(
            stop_reason="end_turn", model="claude-opus-5-5",
            content=[SimpleNamespace(type="text", text=json.dumps(self.answer))])


GOOD = {"cause": "metrics_agent_stuck", "explanation": "restart clears it",
        "actions": ["restart_service"], "risk": "low",
        "human_checks": ["confirm the probe error is gone"]}


def setup(client, answer_override=None):
    world = StuckAgentWorld()
    healer = Healer(world, config="C")
    healer.advisor = Advisor(healer.knowledge, client=client, run_async=False)
    return world, healer


print("Learning and the human-in-the-loop advisor")
print()

client = FakeClient(GOOD)
world, healer = setup(client)
healer.tick()
advice = healer.knowledge.advice()
check("an unmatched failure asks the advisor", client.calls == 1 and len(advice) == 1)
check("advice is stored as pending", advice[0]["status"] == "pending", advice[0]["status"])
check("pending advice does not run", world.restarts == 0)
check("the request names the symptoms",
      json.loads(advice[0]["symptoms"]) == ["probe_failed"], advice[0]["symptoms"])
check("the request asks for schema-constrained output",
      client.kwargs["output_config"]["format"]["type"] == "json_schema")

healer.tick()
check("the same open request is not asked twice", client.calls == 1)
check("still nothing runs before approval", world.restarts == 0)

ok = healer.knowledge.decide_advice(advice[0]["id"], approve=True, who="test")
check("a person can approve pending advice", ok)
healer.tick()
check("approved advice is used as a diagnosis", healer.diagnosis.source == "llm",
      str(healer.diagnosis))
check("approved advice runs its catalogue actions", world.restarts == 1)
check("the repair is verified and recorded as healed",
      healer.events[-1].kind == "healed", healer.events[-1].kind)
check("decided advice cannot be decided again",
      not healer.knowledge.decide_advice(advice[0]["id"], approve=False))

print()
bad = dict(GOOD, actions=["restart_service", "rm_rf_everything"])
client = FakeClient(bad)
world, healer = setup(client)
healer.tick()
stored = healer.knowledge.advice()[0]
check("actions outside the catalogue are dropped from advice",
      json.loads(stored["actions"]) == ["restart_service"], stored["actions"])

risky = dict(GOOD, actions=["rebuild_instance"], risk="low")
client = FakeClient(risky)
world, healer = setup(client)
healer.tick()
stored = healer.knowledge.advice()[0]
check("advice naming a high-risk action is marked high risk", stored["risk"] == "high")
healer.knowledge.decide_advice(stored["id"], approve=True)
healer.tick()
check("approved high-risk advice still waits at the approval gate",
      world.rebuilds == 0 and len(healer.pending_approval) == 1)

world, healer = setup(FakeClient(GOOD))
healer.tick()
healer.knowledge.decide_advice(healer.knowledge.advice()[0]["id"], approve=False)
healer.tick()
check("rejected advice is never used", world.restarts == 0)

print()
world = StuckAgentWorld()
healer = Healer(world, config="C")
healer.advisor = Advisor(healer.knowledge, client=None, run_async=False)
healer.advisor.client = None
healer.tick()
stored = healer.knowledge.advice()
check("without an LLM the request is still recorded for a person",
      len(stored) == 1 and stored[0]["status"] == "pending" and stored[0]["model"] == "none")

world, healer = setup(FakeClient(error=RuntimeError("timeout")))
healer.tick()
stored = healer.knowledge.advice()[0]
check("a failing advisor call is recorded, not raised", stored["status"] == "failed")
healer.tick()
check("the loop keeps ticking after an advisor failure", world.tick_count == 2)

world = StuckAgentWorld()
healer = Healer(world, config="B")
healer.advisor = Advisor(healer.knowledge or __import__("mapek.knowledge").knowledge.Knowledge(),
                         client=FakeClient(GOOD), run_async=False)
healer.tick()
healer.advisor.knowledge.decide_advice(1, approve=True)
healer.tick()
check("config B never uses advice (it has no knowledge stage)", world.restarts == 0)

print()
print("Prevention learned in Knowledge")
world = SimulatedWorld()
healer = Healer(world, config="C")
world.inject("disk_leak")
for _ in range(30):
    healer.tick()
    if world.disk_percent >= 99:
        world.maintenance_restart()
rules = healer.knowledge.rules()
check("a resolved incident becomes a prevention rule", len(rules) == 1, str(rules))
check("the rule fixes the cause, not the symptom",
      json.loads(rules[0]["actions"]) == ["clear_logs", "fix_log_rotation"], rules[0]["actions"])
before = world.downtime_ticks
world.inject("disk_leak")
for _ in range(30):
    healer.tick()
    if world.disk_percent >= 99:
        world.maintenance_restart()
check("the repeat fault is prevented with zero downtime",
      world.downtime_ticks == before, f"{world.downtime_ticks - before} ticks down")
check("prevention is visible as an event",
      any(e.kind == "prevented" for e in healer.events))

print()
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
