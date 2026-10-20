# Human-reviewed HAProxy incident investigation

This extension keeps the same gateway use case. Unknown HTTP failures deserve an investigation rather than a guessed port-range repair. Gemini is an optional advisory analyst, never a broker client or repair approver. The deterministic diagnosis and bounded repair continue without it.

## Operator workflow

1. Open **Incidents** and select the incident. Expand **Investigate with AI**, enter your name and select **Ask AI for an explanation**. Saved reports are available under **Read the AI investigation**.
2. Read the summary, hypotheses, missing evidence, read-only operator checks, proposed remediation, verification and rollback prerequisites. Every model explanation is unverified advice. The model cannot collect additional evidence itself or prove a root cause.
3. Investigate through administrator access. If a repair is necessary outside the qualified catalogue, review and perform it manually. There is no execute-AI-command button.
4. Record the repair performed and the verification evidence/result. This creates an operator-reported Knowledge record, not an independently verified success, incident closure or executable procedure.
5. A new automatic procedure still requires implementation, safety checks, reproducible fault testing and reviewed qualification. Existing two-occurrence promotion rules are unchanged.

The request is asynchronous and must not block monitoring. One provider request can run at a time, requests are separated by 60 seconds, and a completed incident report is not repeatedly regenerated. Provider errors, malformed/truncated responses and timeouts produce an unavailable state without granting authority. In-progress requests interrupted by a controller restart become unavailable and can be retried.

The controller requires fresh supported current observations with matching identity before requesting advice. Otherwise inspect the agent/observer first. Reports now show locally computed safety constraints separately from model text; these describe the submitted evidence and are not a live authorisation. Historical reports remain unchanged. Guidance v2 explains the actual topology, safety thresholds and namespace-only scope. The [42-call comparison](../evidence/diagnosis-quality.md) found improvement but residual errors: read the caveats before using its explanations.

## Configuration and privacy

Disabled by default in a fresh deployment. From the management checkout, run `python3 scripts/configure_investigation.py --model gemini-3.1-flash-lite --key-file /private/path/gemini-key.txt` after deploying the updated controller. This administrator helper uses the existing pinned SSH identities, creates a Kubernetes Secret reference for `GEMINI_API_KEY`, enables the model and permits port 443 only to the provider's currently resolved public IPv4 addresses. It retains namespace default-deny and existing agent/DNS rules. Refresh it if provider DNS changes; an enterprise deployment should use a managed egress proxy with hostname policy. Never put keys in source, a ConfigMap, browser storage or chat. Model availability and a free allowance are not guaranteed. A subsequent full default deployment disables the feature again; explicitly reconfigure it if wanted.

Only allowlisted numeric/boolean gateway measurements leave the lab. Opening and latest same-identity observations may be included, with a freshness flag. Raw logs, addresses, identity strings, errors, configuration, human repair notes, histories, keys and tokens are excluded. This deliberately limits diagnostic depth: certificates, syntax errors and DNS causes cannot be established from these metrics. The next step should be explicit reviewed evidence collectors, not arbitrary model shell access.

Reports remain in private SQLite and backups. UI renders text using `textContent`. Schema validation rejects extra executable fields, but cannot prove the text is correct or free of dangerous suggestions; human review is mandatory. No tools/function calling are enabled. API keys use a header, redirects are refused, replies are capped at 64 KiB, calls time out after 20 seconds and provider error bodies are not exposed.

Google documents structured JSON output, but schema conformance does not establish factual correctness: <https://ai.google.dev/gemini-api/docs/structured-output>. Review current pricing and terms before using real operational information: <https://ai.google.dev/gemini-api/docs/pricing> and <https://ai.google.dev/gemini-api/terms>. Free-tier availability, quotas and data handling vary by service/account and region. This lab sends synthetic numeric evidence only, not bank/customer data.

## Evaluation before claiming benefit

Use labelled cases from the same HAProxy gateway: confirmed port exhaustion, upstream outage, unsafe headroom, reserved-port conflict, stale evidence and unexplained HTTP failure. Compare deterministic rules alone with rules plus Gemini, keeping the evidence identical. Record model/version, input digest, latency, correct hypotheses, unsupported assertions, useful next checks, unsafe suggestions and operator acceptance/corrections. Keep full reports private; publish aggregate scores only. Include provider outage, malformed output and prompt-injection attempts.

Do not call mocked provider tests live model evidence. Unit tests demonstrate privacy filtering, bounded transport and separation from repair authority. The repeated real-provider study is constructed-case evidence with one involved reviewer and in-sample prompt refinement; it does not establish general diagnosis quality. Do not claim additional failure classes are repaired or that model-generated procedures are learned automatically.
