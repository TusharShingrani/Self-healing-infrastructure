"""An LLM advisor with a human in the loop.

When the loop is stuck (no rule matches, a repair did not verify, or every
escalation level is used up) it asks for advice. The advisor asks Claude for a
diagnosis and a plan, and stores the answer in Knowledge as *pending*. Nothing
runs. A person reviews the advice with tools/knowledge.py and approves or
rejects it. Approved advice becomes a diagnosis the loop may use next time the
same symptoms appear.

What keeps this safe:

  - the advisor has no effectors. It cannot run anything, only write advice
  - the response schema restricts actions to the fixed catalogue, so the model
    cannot invent a command. The loop validates the names again before use
  - approved advice still goes through the guardrails and the high-risk
    approval gate like any other plan
  - calls run on a worker thread, so a slow or failing API never stalls the loop

The Anthropic SDK is optional. Without it, or without credentials, a request
is still recorded so a person sees that the loop needed help.
"""

import json
import threading

from .actions import CATALOGUE, HIGH_RISK

try:
    import anthropic
    API_ERRORS = (anthropic.APIError,)
except ImportError:                                   # the SDK is optional
    anthropic = None
    API_ERRORS = ()

MODEL = "claude-opus-5-5"

ACTION_HELP = {
    "restart_service": "systemctl restart nginx on the instance",
    "clear_logs": "delete rotated logs and truncate audit logs over 50 MiB on the bounded log volume",
    "fix_log_rotation": "restore the rotation policy from the reference copy, stop the log producer, rotate once",
    "restore_config": "copy the reference nginx config back, validate it, reload nginx",
    "reboot_instance": "reboot the whole instance through the CloudStack API (high risk, needs approval)",
    "rebuild_instance": "destroy the instance and redeploy it from the clean template (high risk, needs approval)",
}

SYSTEM = f"""You advise a self-healing loop (MAPE-K) that manages nginx on small Ubuntu
lab instances in a CloudStack cloud. The loop is stuck and a human operator will
read your advice before anything happens. You cannot run commands.

Lab facts:
- nginx serves GET /healthz with body "ok". That is the availability check.
- Audit logs live on a bounded 512 MiB loop-backed ext4 volume at /var/log/nginx.
- A lab protocol adds an ExecStartPre preflight: nginx refuses to START with less
  than 25 MiB free on that volume. Stock nginx does not do this; a reload does not
  trigger it, a restart does.
- A frequent logrotate timer keeps the volume small while the rotation policy
  /etc/logrotate.d/nginx-healer exists. A lab fault generator fills the volume when
  that policy is missing.
- The live nginx config is compared with a reference copy.

Symptom names the Monitor stage uses: unreachable, service_down, disk_high,
disk_critical, disk_growing_fast, config_drift, probe_failed.

The only actions that exist (the catalogue):
""" + "\n".join(f"- {name}: {text}" for name, text in ACTION_HELP.items()) + """

Rules for your answer:
- Name the underlying cause, not a symptom. Use snake_case, for example
  service_down_because_disk_full_from_log_growth.
- Choose actions only from the catalogue, in the order to run them. Prefer the
  least disruptive actions that remove the cause. Use an empty list if no
  catalogue action fits, and say in human_checks what a person should do.
- Never propose reboot_instance or rebuild_instance when a guest-level action
  could work.
- Be specific and brief. The operator is a student running an experiment.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "cause": {"type": "string"},
        "explanation": {"type": "string"},
        "actions": {"type": "array",
                    "items": {"type": "string", "enum": sorted(CATALOGUE)}},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "human_checks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["cause", "explanation", "actions", "risk", "human_checks"],
    "additionalProperties": False,
}


class Advisor:
    def __init__(self, knowledge, client=None, model=MODEL, effort="medium",
                 run_async=True):
        self.knowledge = knowledge
        self.model = model
        self.effort = effort
        self.run_async = run_async
        self.client = client if client is not None else self._default_client()
        self.requests = {"ok": 0, "failed": 0, "unavailable": 0}

    @staticmethod
    def _default_client():
        if anthropic is None:
            return None
        try:
            return anthropic.Anthropic(timeout=120.0)
        except Exception:                             # noqa: BLE001
            return None          # no credentials resolvable: record requests only

    @property
    def available(self):
        return self.client is not None

    def request(self, target, reason, symptoms, observation, cause="", recent=()):
        advice_id = self.knowledge.open_advice(target, reason, symptoms)
        if advice_id is None:
            return None                               # already asked, still open
        if self.client is None:
            self.requests["unavailable"] += 1
            self.knowledge.complete_advice(
                advice_id, cause or "unknown", [],
                "No LLM is configured on the healer, so no advice was generated. "
                "A person needs to look at this incident.",
                ["Inspect the instance and decide on a repair by hand."],
                "unknown", "none", status="pending")
            return advice_id
        args = (advice_id, target, reason, symptoms, observation, cause, list(recent))
        if self.run_async:
            threading.Thread(target=self._ask, args=args, daemon=True).start()
        else:
            self._ask(*args)
        return advice_id

    # ------------------------------------------------------------------

    def _prompt(self, target, reason, symptoms, observation, cause, recent):
        safe_obs = {k: v for k, v in observation.items() if k != "probe_error"}
        safe_obs["probe_error"] = str(observation.get("probe_error", ""))[:300]
        return (
            f"Instance: {target}\n"
            f"Why the loop is asking: {reason}\n"
            f"Symptoms now: {sorted(symptoms)}\n"
            f"Rule-based cause, if any: {cause or 'none matched'}\n"
            f"Latest observation: {json.dumps(safe_obs, default=str)}\n"
            f"Recent loop events: {json.dumps(recent, default=str)[:3000]}\n\n"
            "What is the most likely cause, and which catalogue actions should a "
            "person approve?")

    def _ask(self, advice_id, target, reason, symptoms, observation, cause, recent):
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM,
                messages=[{"role": "user", "content": self._prompt(
                    target, reason, symptoms, observation, cause, recent)}],
                output_config={"effort": self.effort,
                               "format": {"type": "json_schema", "schema": SCHEMA}},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            if response.stop_reason == "refusal":
                raise RuntimeError("the model declined to answer")
            if response.stop_reason == "max_tokens":
                raise RuntimeError("the answer was cut off")
            text = next(b.text for b in response.content if b.type == "text")
            data = json.loads(text)
            actions = [a for a in data["actions"] if a in CATALOGUE]
            risk = data["risk"]
            if any(a in HIGH_RISK for a in actions):
                risk = "high"
            self.knowledge.complete_advice(
                advice_id, data["cause"], actions, data["explanation"],
                data["human_checks"], risk, response.model)
            self.requests["ok"] += 1
        except API_ERRORS + (RuntimeError, ValueError, KeyError, TypeError,
                             AttributeError, StopIteration) as error:
            self.requests["failed"] += 1
            self.knowledge.complete_advice(
                advice_id, cause or "unknown", [],
                f"The advisor call failed: {type(error).__name__}: {str(error)[:300]}",
                ["Inspect the instance and decide on a repair by hand."],
                "unknown", self.model, status="failed")
