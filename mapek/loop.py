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
        self.open_incident = None       # {"tick", "early_signs"}
        self._attempts = {}             # cause -> escalation level already tried

    # ------------------------------------------------------------------

    def tick(self):
        """Exactly one iteration. One primary observation per tick."""
        self.world.step()
        observation = self.world.observe(sample=True)
        healthy = self.world.health(observation)
        self.world.note_health(healthy)

        now = observation["tick"]
        symptoms = self.monitor.symptoms(observation)
        if not symptoms:
            self._attempts.clear()
            return

        if healthy:
            self._handle_early_signs(now, symptoms)
            return

        if self.config == "A":
            self._log(LoopEvent(now, "observed",
                                "failure seen, no healing enabled", symptoms))
            return

        diagnosis = self.analyser.analyse(
            symptoms, self.knowledge if self.config == "C" else None)
        if diagnosis is None or diagnosis.cause == "unknown":
            self._log(LoopEvent(now, "escalated", "no diagnosis matched", symptoms))
            return

        level = self._attempts.get(diagnosis.cause, 0)
        actions = self.planner.plan(diagnosis, attempt=level)
        if not actions:
            self._log(LoopEvent(now, "escalated",
                                f"all {self.planner.levels(diagnosis.cause)} repair "
                                f"levels exhausted, a person is needed",
                                symptoms, diagnosis.cause, level=level))
            return

        self._act(now, symptoms, diagnosis.cause, actions, kind="healed",
                  source=diagnosis.source, level=level)

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

        results = self.executor.execute(actions)
        self.guardrails.record(actions, now)
        ok = all(r.ok for r in results) and self.executor.verify()
        detail = "; ".join(f"{r.action}: {r.detail}" for r in results)

        if not ok:
            # this repair level did not work, so the next attempt escalates
            self._attempts[cause] = level + 1
            self._log(LoopEvent(now, "escalated",
                                "repair did not verify: " + detail,
                                symptoms, cause, actions, level))
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
