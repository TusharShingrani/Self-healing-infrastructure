# Advisory investigation validation — 18 October 2026

## Implemented and tested

- 87 unit tests pass on Windows and the management Linux host, including 11 advisory tests. These cover privacy filtering, freshness/identity handling, bounded response schema/transport, redirects, provider errors, unknown incidents, deduplication and the inability of advice/manual notes to approve or qualify a repair.
- A real `gemini-3.1-flash-lite` call returned a valid structured report for synthetic numeric evidence. The older 2.5 Flash name was refused for this account; another model did not finish within the deadline. Model availability and latency must be tested, not assumed from unit tests.
- The updated controller is deployed. Gemini is enabled through a Secret environment reference and a separate destination-IP-limited HTTPS egress rule, preserving default-deny. Agent, host broker, HAProxy process and runtime repair catalogue were unchanged.
- An authenticated API request investigated an existing real gateway incident. Its structured Gemini report was stored privately in Knowledge. Monitoring remained responsive, duplicate requests were refused, and execution records and qualified procedures were unchanged.
- Post-deployment acceptance passed: 11 healthy monitoring targets, populated gateway dashboard panels, fresh independent transactions, healthy baseline range and idle backend, mTLS enforcement, monitor write refusal, unsigned-intent refusal, three Ready nodes and two constrained runtime Pods.

## Deployment finding

The first controller image failed because privately staged source permissions prevented the non-root runtime from reading Python files. The previous controller was restored. The image now explicitly grants source read/traverse permissions before dropping to the runtime user, and the corrected rollout passed. The failed rollout briefly interrupted the controller; it did not restart the gateway or change the broker. This is a deployment defect and recovery, not a successful self-healing experiment.

## Evidence boundary

These checks prove integration and separation of authority, not diagnostic accuracy or reduced investigation time. No new failure class is qualified for automatic repair. No real operator investigation time was measured. The new browser controls were deployed, but a signed-in visual browser review was not performed in this validation; the authenticated HTTP workflow was exercised directly. Manual repair capture was unit-tested without inventing a live human repair.

The actual reports, incident identifiers and recovery archives remain private/off-platform. A labelled, repeated evaluation against deterministic-only diagnosis is still required before claiming the LLM improves diagnosis. See the rubric in [AI investigation](../docs/ai-investigation.md).
