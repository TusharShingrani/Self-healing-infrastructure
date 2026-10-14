"""The four active MAPE stages. Knowledge lives in knowledge.py.

Each stage is one small class with one job, so the code reads like the theory:

  Monitor   turns raw probes into symptoms
  Analyse   turns symptoms into a diagnosis (a cause, not a symptom)
  Plan      turns a diagnosis into an ordered list of approved actions
  Execute   runs those actions through the effectors and verifies the result
"""

from dataclasses import dataclass, field


# ----------------------------------------------------------------- Monitor

class Monitor:
    """Reads the probes and names what looks wrong.

    A symptom is an observation, not a cause. "disk above 95 percent" is a
    symptom. "log rotation is broken" is a cause, and that is Analyse's job.
    """

    def __init__(self, disk_warn=80.0, disk_critical=95.0, growth_warn=2.0):
        self.disk_warn = disk_warn
        self.disk_critical = disk_critical
        self.growth_warn = growth_warn

    def symptoms(self, observation):
        """Names what looks wrong. A value of None means the probe failed, and
        a failed probe is never treated as a healthy reading."""
        found = []
        if not observation.get("reachable", True):
            return ["unreachable"]

        if observation.get("service_running") is False:
            found.append("service_down")

        disk = observation.get("disk_percent")
        if disk is not None:
            if disk >= self.disk_critical:
                found.append("disk_critical")
            elif disk >= self.disk_warn:
                found.append("disk_high")

        growth = observation.get("disk_growth")
        if growth is not None and growth >= self.growth_warn:
            found.append("disk_growing_fast")

        if observation.get("config_correct") is False:
            found.append("config_drift")

        if observation.get("http_ok") is False:
            found.append("http_unavailable")
        for name, passed in observation.get('infrastructure_checks', {}).items():
            if passed is False:
                found.append('infra:' + name)

        if observation.get("probe_error"):
            found.append("probe_failed")
        return found


# ----------------------------------------------------------------- Analyse

@dataclass
class Diagnosis:
    cause: str
    confidence: float
    evidence: list = field(default_factory=list)
    source: str = "rules"       # "rules", "knowledge" or "llm"
    actions: list = field(default_factory=list)   # set only for approved advice


class RuleAnalyser:
    """Maps a set of symptoms to a cause.

    Order matters: the most specific rule wins, because a symptom set can
    match several rules and the first match should be the deepest cause.
    """

    RULES = [
        # (required symptoms, cause, confidence)
        ({"unreachable"}, "instance_unreachable", 0.9),
        ({"service_down", "disk_critical", "disk_growing_fast"},
         "service_down_because_disk_full_from_log_growth", 0.9),
        ({"service_down", "disk_critical"},
         "service_down_because_disk_full", 0.8),
        ({"disk_high", "disk_growing_fast"},
         "disk_filling_from_log_growth", 0.8),
        ({"config_drift"}, "manual_configuration_change", 0.95),
        ({"service_down"}, "service_stopped", 0.6),
        ({"disk_critical"}, "disk_full", 0.7),
    ]

    def analyse(self, symptoms, knowledge=None):
        symptom_set = set(symptoms)
        if not symptom_set:
            return None

        # Knowledge first: if this exact pattern was seen before and the fix
        # worked, reuse it. This is the K in MAPE-K doing real work.
        if knowledge:
            prior = knowledge.recall(symptom_set)
            if prior:
                return Diagnosis(prior["cause"], 0.95, sorted(symptom_set), "knowledge")

        for required, cause, confidence in self.RULES:
            if required <= symptom_set:
                return Diagnosis(cause, confidence, sorted(symptom_set), "rules")

        # Rules had nothing. Advice from the LLM advisor that a person has
        # approved is the last source, and it only ever names catalogue actions.
        if knowledge and hasattr(knowledge, "approved_advice"):
            advised = knowledge.approved_advice(symptom_set)
            if advised:
                return Diagnosis(advised["cause"], 0.7, sorted(symptom_set), "llm",
                                 actions=advised["actions"])
        return Diagnosis("unknown", 0.0, sorted(symptom_set), "rules")


# -------------------------------------------------------------------- Plan

class Planner:
    """Chooses actions for a cause, from a fixed catalogue.

    The planner may only return names that exist in the catalogue. It can
    never invent a command. That constraint is what makes the loop auditable.

    Plans are ordered by escalation level. Level 0 is the guest-level repair.
    If that has already been tried for this cause and the system is still
    unhealthy, the planner moves up: reboot the instance, then rebuild it from
    the clean template. The higher levels are high risk, so the loop requires
    approval before running them.
    """

    PLANS = {
        "service_down_because_disk_full_from_log_growth": [
            ["clear_logs", "fix_log_rotation", "restart_service"],
            ["reboot_instance"],
            ["rebuild_instance"],
        ],
        "service_down_because_disk_full": [
            ["clear_logs", "restart_service"],
            ["reboot_instance"],
            ["rebuild_instance"],
        ],
        "disk_filling_from_log_growth": [
            ["clear_logs", "fix_log_rotation"],
        ],
        "manual_configuration_change": [
            ["restore_config"],
            ["rebuild_instance"],
        ],
        "service_stopped": [
            ["restart_service"],
            ["reboot_instance"],
            ["rebuild_instance"],
        ],
        "disk_full": [
            ["clear_logs"],
        ],
        "instance_unreachable": [
            ["reboot_instance"],
            ["rebuild_instance"],
        ],
    }

    def __init__(self, catalogue):
        self.catalogue = catalogue
        for cause, levels in self.PLANS.items():
            for actions in levels:
                unknown = [a for a in actions if a not in catalogue]
                if unknown:
                    raise ValueError(
                        f"plan for {cause} uses actions not in the catalogue: "
                        f"{unknown}")

    def plan(self, diagnosis, attempt=0):
        """Return the actions for this escalation level, or [] if exhausted."""
        if diagnosis.actions and diagnosis.cause not in self.PLANS:
            # approved advice: one level, catalogue names only
            if attempt > 0:
                return []
            unknown = [a for a in diagnosis.actions if a not in self.catalogue]
            if unknown:
                raise ValueError(f"advice uses actions not in the catalogue: {unknown}")
            return list(diagnosis.actions)
        levels = self.PLANS.get(diagnosis.cause, [])
        if attempt >= len(levels):
            return []
        return levels[attempt]

    def levels(self, cause):
        return len(self.PLANS.get(cause, []))


# ----------------------------------------------------------------- Execute

@dataclass
class ActionResult:
    action: str
    ok: bool
    detail: str


class Executor:
    """Runs approved actions and verifies the outcome.

    Verification matters more than the action. An action that reports success
    while the service is still down is the failure mode that makes automation
    dangerous, so the loop always checks the world afterwards.
    """

    def __init__(self, world, catalogue):
        self.world = world
        self.catalogue = catalogue

    def execute(self, actions):
        results = []
        for name in actions:
            effector = self.catalogue[name]
            try:
                ok, detail = effector(self.world)
            except Exception as error:              # noqa: BLE001
                # a failing effector must become a recorded outcome, never an
                # exception that takes the loop down
                ok, detail = False, f"{type(error).__name__}: {error}"
            results.append(ActionResult(name, ok, detail))
            if not ok:
                break
        return results

    def verify(self):
        """Check the world again after acting.

        Uses sample=False so this extra reading does not reset the
        rate-of-change state that the next tick depends on.
        """
        observation = self.world.observe(sample=False)
        return self.world.health(observation)
