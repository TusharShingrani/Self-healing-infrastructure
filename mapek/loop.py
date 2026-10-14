"""The MAPE-K loop itself.

One iteration, with exactly one primary observation:

    step (time) -> observe -> health -> symptoms
                                 |
            prevention? ---------+--------- diagnosis -> plan (escalation level)
                                                           |
                                        guardrails + approval gate
                                                           |
                                      execute -> verify -> record

Configurations, used by the experiment:

    A   no healing. The loop only watches and records.
    B   healing with rules. Detect, diagnose, repair, verify, escalate.
    C   healing with rules plus knowledge. Adds recall and prevention.
"""

import time
from collections import Counter
from dataclasses import dataclass, field

from .actions import CATALOGUE, HIGH_RISK
from .guardrails import Guardrails
from .knowledge import Knowledge
from .stages import Monitor, RuleAnalyser, Planner, Executor


@dataclass
class LoopEvent:
    tick: int
    kind: str          # observed | prevented | healed | blocked | escalated
    detail: str = ""
    symptoms: list = field(default_factory=list)
    cause: str = ""
    actions: list = field(default_factory=list)
    level: int = 0


class Healer:
    def __init__(self, world, config="C", knowledge_path=":memory:",
                 auto_approve=True, approve_high_risk=False, verbose=False):
        if config not in ("A", "B", "C"):
            raise ValueError("config must be A, B or C")
        self.world = world
        self.config = config
        self.verbose = verbose

        # High-risk actions reboot or destroy a whole instance. The loop will
        # not run them unless a human has explicitly enabled it for this run.
        self.approve_high_risk = approve_high_risk

        self.monitor = Monitor()
        self.analyser = RuleAnalyser()
        self.planner = Planner(CATALOGUE)
        self.executor = Executor(world, CATALOGUE)
        self.guardrails = Guardrails()
        self.knowledge = Knowledge(knowledge_path, auto_approve) \
            if config == "C" else None

        self.events = []
        self.pending_approval = []      # proposals a human must authorise
        self.operator = None           # optional persistent incident-review gate
        self.open_incident = None       # {"tick", "early_signs"}
        self._attempts = {}             # cause -> escalation level already tried

        # Visibility only. None of this changes what the loop decides; it lets
        # the runner publish what each MAPE stage did on the last tick.
        self.on_event = None            # callable(LoopEvent), set by a runner
        self.advisor = None             # optional, advice only, never executes
        self.last_observation = {}
        self.last_symptoms = []
        self.last_healthy = None
        self.diagnosis = None           # Diagnosis of the current problem
        self.stage_seconds = {}
        self.diagnoses_by_source = Counter()
        self.action_counts = Counter()  # (action, "ok" | "failed") -> count

    # ------------------------------------------------------------------

    def tick(self):
        """Exactly one iteration. One primary observation per tick."""
        self.stage_seconds = {}
        started = time.monotonic()

        # ---- Monitor: one reading, turned into named symptoms
        self.world.step()
        observation = self.world.observe(sample=True)
        healthy = self.world.health(observation)
        self.world.note_health(healthy)

        now = observation["tick"]
        symptoms = self.monitor.symptoms(observation)
        self.last_observation, self.last_symptoms = observation, symptoms
        self.last_healthy = healthy
        self.stage_seconds["monitor"] = time.monotonic() - started
        if not symptoms:
            if self.operator is not None:
                self.operator.reconcile(self.world, observation)
            self._attempts.clear()
            self.diagnosis = None
            return

        if healthy:
            self._handle_early_signs(now, symptoms)
            return

        if self.config == "A":
            self._log(LoopEvent(now, "observed",
                                "failure seen, no healing enabled", symptoms))
            return

        # ---- Analyse: symptoms to a cause, from knowledge first, then rules
        mark = time.monotonic()
        diagnosis = self.analyser.analyse(
            symptoms, self.knowledge if self.config == "C" else None)
        self.stage_seconds["analyse"] = time.monotonic() - mark
        self.diagnosis = diagnosis
        if diagnosis is None or diagnosis.cause == "unknown":
            if self.operator is not None:
                self.operator.capture(self.world, symptoms, 'unknown', [], observation)
            self._log(LoopEvent(now, "escalated", "no diagnosis matched", symptoms))
            self._ask_advisor("no diagnosis matched", symptoms, observation)
            return
        self.diagnoses_by_source[diagnosis.source] += 1

        # ---- Plan: the actions for this escalation level, from the catalogue
        mark = time.monotonic()
        level = self._attempts.get(diagnosis.cause, 0)
        actions = self.planner.plan(diagnosis, attempt=level)
        self.stage_seconds["plan"] = time.monotonic() - mark
        if not actions:
            self._log(LoopEvent(now, "escalated",
                                f"all {self.planner.levels(diagnosis.cause)} repair "
                                f"levels exhausted, a person is needed",
                                symptoms, diagnosis.cause, level=level))
            self._ask_advisor("repair levels exhausted", symptoms, observation,
                              diagnosis.cause)
            return

        # ---- Execute: guardrails, approval gate, act, verify, record
        mark = time.monotonic()
        self._act(now, symptoms, diagnosis.cause, actions, kind="healed",
                  source=diagnosis.source, level=level)
        self.stage_seconds["execute"] = time.monotonic() - mark

    def _ask_advisor(self, reason, symptoms, observation, cause=""):
        """Advice only. The advisor records a suggestion for a human; it never
        runs anything, and a slow or failing advisor never stalls the loop."""
        if self.advisor is None:
            return
        try:
            if self.operator is not None:
                observation = dict(observation)
                cases = [c for c in self.operator.cases()
                         if c['target'] == getattr(self.world, 'name', 'simulated')]
                if cases:
                    import json
                    observation['incident_evidence'] = json.loads(cases[0]['evidence'])
            self.advisor.request(
                target=getattr(self.world, "name", "simulated"), reason=reason,
                symptoms=symptoms, observation=observation, cause=cause,
                recent=[e.__dict__ for e in self.events[-8:]])
        except Exception:                             # noqa: BLE001
            pass

    def escalation_level(self):
        if self.diagnosis is None:
            return 0
        return self._attempts.get(self.diagnosis.cause, 0)

    # ------------------------------------------------------------------

    def _handle_early_signs(self, now, symptoms):
        """The system still works, but something looks wrong."""
        if self.config == "C":
            match = self.knowledge.prevention_match(symptoms)
            if match:
                self._act(now, symptoms, match["cause"], match["actions"],
                          kind="prevented")
                return
        if self.open_incident is None:
            # Keep the EARLIEST symptom set, not the union of everything seen
            # on the way down. A prevention rule learned from the union would
            # only fire once the system was already nearly broken, which
            # defeats the point of prevention.
            self.open_incident = {"tick": now, "early_signs": set(symptoms)}

    def _act(self, now, symptoms, cause, actions, kind, source="rules", level=0):
        if self.operator is not None:
            self.operator.capture(self.world, symptoms, cause, actions, self.last_observation)
        risky = [a for a in actions if a in HIGH_RISK]
        if risky and not self.approve_high_risk:
            # Waiting for approval must not consume the escalation level. The
            # level advances only when an executed repair fails verification,
            # otherwise two unapproved ticks would silently burn through reboot
            # and rebuild without either ever running.
            proposal = {
                "tick": now,
                "target": getattr(self.world, "name", "simulated"),
                "cause": cause,
                "actions": list(actions),
                "symptoms": sorted(symptoms),
                "level": level,
            }
            if not any(p["cause"] == cause and p["actions"] == proposal["actions"]
                       and p["level"] == level and p["target"] == proposal["target"]
                       for p in self.pending_approval):
                self.pending_approval.append(proposal)
                self._log(LoopEvent(now, "escalated",
                                    f"approval required for {', '.join(risky)} "
                                    f"on {proposal['target']}",
                                    symptoms, cause, actions, level))
            return

        allowed, reason = self.guardrails.check(actions, now)
        if not allowed:
            self._log(LoopEvent(now, "blocked", reason, symptoms, cause,
                                actions, level))
            return

        if self.operator is not None:
            allowed, reason = self.operator.authorize(self.world, symptoms, cause,
                                                      actions, self.last_observation)
            if not allowed:
                self._log(LoopEvent(now, 'blocked', reason, symptoms, cause, actions, level))
                return

        results = self.executor.execute(actions)
        for r in results:
            self.action_counts[(r.action, "ok" if r.ok else "failed")] += 1
        self.guardrails.record(actions, now)
        ok = all(r.ok for r in results) and self.executor.verify()
        if self.operator is not None:
            ok = self.operator.finish(self.world, ok) and ok
        detail = "; ".join(f"{r.action}: {r.detail}" for r in results)

        if not ok:
            # this repair level did not work, so the next attempt escalates
            self._attempts[cause] = level + 1
            self._log(LoopEvent(now, "escalated",
                                "repair did not verify: " + detail,
                                symptoms, cause, actions, level))
            self._ask_advisor("repair did not verify: " + detail, symptoms,
                              self.last_observation, cause)
            if self.knowledge:
                self.knowledge.record(symptoms, [], cause, source, actions,
                                      "failed", 0)
            self.open_incident = None
            return

        self._attempts.pop(cause, None)
        self._log(LoopEvent(now, kind, detail, symptoms, cause, actions, level))

        if self.knowledge:
            early = self.open_incident["early_signs"] if self.open_incident else set()
            opened = self.open_incident["tick"] if self.open_incident else now
            self.knowledge.record(symptoms, early, cause, source, actions,
                                  "resolved", now - opened)
        self.open_incident = None

    def _log(self, event):
        self.events.append(event)
        if self.on_event is not None:
            self.on_event(event)
        if self.verbose:
            marker = {"healed": "FIXED", "prevented": "PREVENTED",
                      "blocked": "BLOCKED", "escalated": "ESCALATED",
                      "observed": "SEEN"}[event.kind]
            level = f"L{event.level} " if event.level else ""
            print(f"  t={event.tick:>3}  {marker:<10} {level}{event.cause or ''} "
                  f"{event.detail}")

    # ------------------------------------------------------------------

    def run(self, ticks):
        for _ in range(ticks):
            self.tick()
        return self.events
