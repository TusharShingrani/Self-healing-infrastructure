# Operations console redesign

The owner requested a technical but understandable console. Claude was consulted through the owner's authorised browser conversation for design critique, using a public project description. During that design consultation Claude did not inspect the repository, implement code or receive private incident histories or credentials.

The implemented design uses a compact neutral slate shell, Overview/Incidents/Knowledge navigation, secondary audit and a settings drawer. Measurements replace oversized verdict cards. Incident detail separates deterministic evidence, violet advisory AI text, the fixed decision and independent verification. The MAPE-K ledger is a record, not an animated progress indicator.

The API does not expose p95 latency, historical source-port series, separate analysis time or lease-expiry time. These were not fabricated. Actual fresh same-identity counter differences show their observation interval; resets, stale evidence and identity changes invalidate the baseline. Grafana supplies trends. No unsupported Reject control was added.

Validation: all 101 tests pass locally and in CI with Node. The management host executes 96 successfully and skips five Node tests. The suite includes five production UI view-model tests covering missing/stale/future observations, admission prerequisites, counter resets and identity changes, current-scope procedure selection and post-failure qualification counts. Healthy, pending and stale synthetic browser fixtures were inspected; fixture data is not live recovery evidence. This presentation change does not extend the repair catalogue.

On 20 October Claude separately reviewed the public repository read-only. Its review covered the principal guides, diagrams, UI labels and monitoring configuration, rather than every source/evidence file. See the [completion review](completion-review.md).
