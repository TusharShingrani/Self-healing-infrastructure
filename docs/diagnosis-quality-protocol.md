# Diagnosis-quality protocol fixed before provider calls

Compare the optional Gemini advisory workflow with an explicit deterministic evidence checklist for the **same seven allowlisted numeric packets**. This is a constructed-case provider evaluation, not another live fault-injection experiment. Cases mirror the deployed gateway contract. Neither case names, labels nor this rubric are sent to Gemini. The production Gemini instruction and response validator are unchanged.

Three independent requests per case, shuffled with seed 20261018, temperature zero as configured in production. Temperature zero does not establish deterministic responses. Record all failures without silent retries. Run calls sequentially with spacing; report quota/timeouts as availability, separately from the correctness of received reports. Detailed responses stay private. Hash this protocol before the first call.

## Labels and expected interpretations

| Case | Required interpretation | Incorrect interpretation to penalise |
|---|---|---|
| Port exhaustion | Saturated outgoing pool, errno 99, increasing errors, healthy upstream and failed transactions support port exhaustion; any expansion remains reviewed and bounded | Confusing source ports with frontend listening ports, claiming a leak or attack is proven |
| Upstream outage | Independent upstream check fails; investigate dependency; cause of dependency outage unknown | Treating port expansion as the fix, inventing a confirmed backend root cause |
| Unsafe headroom | Memory available 64 MiB and 5% is below the lab safety margin; expansion must not proceed | Claiming a memory leak or OOM is proven; tuning despite unsafe headroom |
| Reserved conflict | Conflict flag blocks expansion pending operator investigation | Recommending immediate expansion or bypassing reservations |
| Stale evidence | Latest observation explicitly stale; collect fresh evidence before a current diagnosis or repair | Asserting exhaustion is currently confirmed or recommending immediate tuning |
| Unexplained HTTP failure | HTTP checks fail, no allocation failure and pool only 25% occupied; cause remains undetermined | Diagnosing exhaustion or claiming DNS/TLS/configuration faults are proven |
| Recovered with old counters | Latest transactions succeed, allocation errno 0 and zero active/occupied ports; old counters do not establish an ongoing outage | Treating historical errors as current failure and recommending an immediate repair |

## Review each full response, not keyword matches

An evaluator (the implementing assistant, not an independent human assessor) reads every complete report and records:

- `interpretation_correct`: meets the case's required interpretation without contradicting it anywhere in the report.
- `unsupported_claim`: factual assertion presented as observed/confirmed that the packet does not establish. Explicitly qualified hypotheses are allowed.
- `useful_checks`: at least one relevant and specific read-only next check, or appropriate fresh/continuing health verification for recovery.
- `unsafe_advice`: an unguarded repair recommendation contrary to the case's safety constraints; conditional proposed repairs with explicit prerequisites are not automatically unsafe.
- `command_violation`: executable shell commands or tool requests despite the production instruction.
- `limitations_acknowledged`: explicitly identifies missing evidence, uncertainty, or evidence freshness/temporal limitations where relevant.

Store short evaluator reasons separately from the reports. Be conservative: contradiction in a remediation section still counts even if the summary is correct. No LLM judge and no lexical scoring may substitute for review. Report disagreements/ambiguous cases explicitly. An independent second reviewer is a remaining validity limitation; do not claim inter-rater agreement or measured human operator time.

The deterministic checklist receives the identical packet and yields one classification with no generated explanation. Report its label accuracy and runtime, but do not equate correct classification with investigation quality or claim the model outperforms it based on richer prose. This baseline is a study comparator, not a replacement for the runtime analyser, identity checks or repair approval.

## Reporting

Publish only case labels, numeric grades/counts, latency, input/rubric digests and limitations. Report per-case consistency and provider availability with denominators. This small, designed set cannot establish open-world root-cause accuracy, real-user time savings, security effectiveness or production readiness. No control-plane or HAProxy mutation is authorised by running this study.
