# Completion review — 20 October 2026

## Verdict

The implemented single-use-case research PoC is functionally demonstrated: a Kubernetes-hosted MAPE-K controller and node agent manage outgoing source-port exhaustion of a real VM-hosted HAProxy service. The native root broker admits only a fixed namespace range change. This is a scoped feasibility prototype, not a completed enterprise resilience product.

Live evidence includes a nine-trial mode comparison, three paired restart comparisons, wrong-repair refusals, independent request verification and a 42-call constructed-case Gemini study. These results and their limits remain in the dated evidence files. The current console/dashboard passed acceptance on 19 and 20 October. No new recovery trial should be inferred from presentation-only acceptance.

## Review and corrections

Claude reported reading the public `main` tree at `0efad89` read-only. It read README, AGENTS, the principal architecture/design/install/security/research/operator/demo/AI guides and validation/operator-usability/restart evidence. It checked UI labels, monitoring configuration, test/CI counts and the observer-fetch route. It partly read the AI study evidence and did not review every source or evidence file. Codex independently checked the relevant production code and cross-file references. This was an assisted consistency review, not an independent security audit.

| Finding | Correction |
|---|---|
| README bypassed broker in independent evidence route | Broker now pulls the observer over mTLS, consistent with plugins/gateway.py and architecture.md |
| Old console and dashboard names in demo/AI guide | Current Overview, Incidents, Knowledge, Settings and exact action labels |
| Historical panel/test counts read as current | Dated supersession notes and a separate current acceptance section |
| Qualification omitted post-failure condition | Two distinct verified occurrences after the last failure in the exact scope, plus explicit promotion |
| Mode labels differed | UI/API mapping table in operator guide |
| AGENTS implied Kubernetes itself was healed | Explicit VM-hosted gateway target and Kubernetes-hosted control software |
| Claude's first verdict inferred no live rollout from missing public record | Corrected using actual 19 October rollout/browser checks and 20 October acceptance; documentation gap rather than evidence of a missing deployment |

## Remaining limits

- Only namespace source-port exhaustion has a qualified gateway repair. Backend outage, unsafe headroom, conflicts, stale evidence and unknown HTTP failures do not gain an automatic fix.
- The temporary capacity increase does not remove a leak or establish predictive prevention. Correct static sizing remains an important simpler alternative.
- Procedural learning reuses explicitly reviewed outcomes for an exact identity/policy scope. Gemini neither trains itself nor creates executable repair procedures.
- Named operator labels share one private token. Corporate identity and independent separation of duties are absent.
- One gateway, controller, PVC and K3s server remain availability dependencies. No fleet or HA claim.
- Full disaster reconstruction, independent usability evaluation, certificate lifecycle and production workload qualification remain future work.
- DORA is a governance mapping, not compliance evidence.

## Demo readiness

Use docs/demo.md and the operator guide. Recheck baseline and acceptance before recording. Keep video, detailed histories, screenshots and recovery archives private on the laptop. A recorded demonstration is illustrative evidence, not additional repetitions of the comparative study. Never silently turn a refused demonstration into a safety bypass.
