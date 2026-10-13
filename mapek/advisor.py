"""An LLM advisor with a human in the loop.

When the loop is stuck (no rule matches, a repair did not verify, or every
escalation level is used up) it asks for advice. The advisor asks an LLM for a
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

The provider is pluggable: anything with ask(system, prompt) -> (dict, model).
The default is Google Gemini over its REST API, standard library only, enabled
by GEMINI_API_KEY in the environment. Without a provider, a request is still
recorded so a person sees that the loop needed help.

Note for the report: on Gemini's free tier, Google may use prompts to improve
its products. The prompt contains symptoms and lab metrics only, never
credentials.
"""

import json
import os
import threading
import urllib.error
import urllib.request

from .actions import CATALOGUE, HIGH_RISK

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


# The answer the model must give. Gemini's responseSchema uses the OpenAPI
# subset with upper-case type names; "enum" pins actions to the catalogue.
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "cause": {"type": "STRING"},
        "explanation": {"type": "STRING"},
        "actions": {"type": "ARRAY",
                    "items": {"type": "STRING", "enum": sorted(CATALOGUE)}},
        "risk": {"type": "STRING", "enum": ["low", "medium", "high"]},
        "human_checks": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["cause", "explanation", "actions", "risk", "human_checks"],
    "propertyOrdering": ["cause", "explanation", "actions", "risk", "human_checks"],
}

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODEL = "gemini-3.5-flash-lite"   # 2.5 closed to new keys; larger Flash models 503 under free-tier load


class AdvisorError(RuntimeError):
    pass


class GeminiProvider:
    """Google Gemini through its REST API. The key travels in a header, never
    in the URL, so it cannot end up in a log line or an error message."""

    def __init__(self, api_key, model=None, timeout=60, opener=None):
        self.api_key = api_key
        self.model = model or os.environ.get("HEALER_GEMINI_MODEL") or GEMINI_MODEL
        self.timeout = timeout
        self._open = opener or urllib.request.urlopen

    def ask(self, system, prompt):
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json",
                                 "responseSchema": SCHEMA,
                                 "temperature": 0.2},
        }
        request = urllib.request.Request(
            GEMINI_URL.format(model=self.model), data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "x-goog-api-key": self.api_key}, method="POST")
        try:
            with self._open(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:300]
            hint = {404: f" (model {self.model} not available to this key, set HEALER_GEMINI_MODEL)",
                    429: " (free-tier quota or rate limit)",
                    503: " (model overloaded, try later or a lighter model)"}.get(error.code, "")
            raise AdvisorError(f"Gemini returned HTTP {error.code}{hint}: {detail}") from None
        except (urllib.error.URLError, OSError) as error:
            raise AdvisorError(f"Gemini unreachable: {error}") from None

        blocked = payload.get("promptFeedback", {}).get("blockReason")
        if blocked:
            raise AdvisorError(f"Gemini blocked the prompt: {blocked}")
        candidates = payload.get("candidates") or []
        if not candidates:
            raise AdvisorError("Gemini returned no answer")
        candidate = candidates[0]
        finish = candidate.get("finishReason", "STOP")
        if finish != "STOP":
            raise AdvisorError(f"Gemini stopped early: {finish}")
        # thinking models may return thought parts first; only answer text counts
        text = "".join(part.get("text", "")
                       for part in candidate.get("content", {}).get("parts", [])
                       if not part.get("thought"))
        return json.loads(text), payload.get("modelVersion", self.model)


def default_provider():
    key = os.environ.get("GEMINI_API_KEY")
    return GeminiProvider(key) if key else None


class Advisor:
    def __init__(self, knowledge, provider="default", run_async=True):
        self.knowledge = knowledge
        self.run_async = run_async
        self.provider = default_provider() if provider == "default" else provider
        self.requests = {"ok": 0, "failed": 0, "unavailable": 0}

    @property
    def available(self):
        return self.provider is not None

    def request(self, target, reason, symptoms, observation, cause="", recent=()):
        advice_id = self.knowledge.open_advice(target, reason, symptoms)
        if advice_id is None:
            return None                               # already asked, still open
        if self.provider is None:
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
        model = getattr(self.provider, "model", "unknown")
        try:
            data, model = self.provider.ask(SYSTEM, self._prompt(
                target, reason, symptoms, observation, cause, recent))
            # validate again: the schema is a request, not a guarantee
            actions = [a for a in data["actions"] if a in CATALOGUE]
            risk = data["risk"] if data["risk"] in ("low", "medium", "high") else "high"
            if any(a in HIGH_RISK for a in actions):
                risk = "high"
            self.knowledge.complete_advice(
                advice_id, str(data["cause"]), actions, str(data["explanation"]),
                [str(c) for c in data["human_checks"]], risk, model)
            self.requests["ok"] += 1
        except (AdvisorError, ValueError, KeyError, TypeError,
                AttributeError) as error:
            self.requests["failed"] += 1
            self.knowledge.complete_advice(
                advice_id, cause or "unknown", [],
                f"The advisor call failed: {type(error).__name__}: {str(error)[:300]}",
                ["Inspect the instance and decide on a repair by hand."],
                "unknown", model, status="failed")
