# Real HAProxy gateway validation — 17 October 2026

## Environment and evidence boundary

Ubuntu 24.04, Linux 6.8.0-106-generic, cgroup v2, K3s v1.36.5+k3s1 and distribution HAProxy 2.8.16-0ubuntu0.24.04.3. Six retained VMs; three Ready Kubernetes nodes. The protected single K3s server uses SQLite. The real gateway runs as a constrained non-root host service in a dedicated namespace; its upstream is a bounded test instrument, not banking software. Reduced port range, server-close mode and disabled backend reuse deliberately expose the allocation boundary; these are not claims about stock/default or pooled banking traffic.

## Final repeated live comparison

Two reviewed qualification occurrences preceded nine seeded-order trials: three observe-only, three reviewed and three automatic. Each trial used the same 24-second, 64-background-connection load. A separate VM measured nonce-checked HTTP requests through HAProxy. The table excludes qualification runs.

| Mode | Trials | Failed independent client checks / all checks | Median time to stable client recovery |
|---|---:|---:|---:|
| observe | 3 | 64/64 | No recovery within load window |
| reviewed | 3 | 23/65 | 8.811 s |
| automatic | 3 | 13/66 | 4.401 s |

Recovery is the first of three consecutive successful independent HTTP checks while background load remains active; it is not the instant a sysctl changes. Reviewed approval after two seconds is scripted protocol, not real operator response time. Automatic trials used the promoted procedure without a new approval. The final controller separately required three distinct successful observations spanning at least two seconds before marking repair verified. This is one seeded order, not a balanced crossover design; socket TIME_WAIT and environmental variation can differ despite baseline/readiness checks.

All treated occurrences verified while load continued, with unchanged gateway identity and host port range. The namespace returned to baseline between runs; no gateway restart/reload was the repair. Observe-only trials made no mutation and did not recover within the active load window. Per-trial numeric data are in [gateway-comparison.json](gateway-comparison.json). This small comparison is descriptive feasibility evidence, not statistical superiority, production throughput, predictive prevention or zero-loss proof.

The preceding development comparison also passed all nine trials. The final comparison was repeated after tightening independent-client diagnosis and verification, rather than treating earlier code's results as validation of those changes. Detailed histories remain private.

## Refusal, transport and monitoring acceptance

- Live unavailable-upstream diagnosis produced no tuning. A separate valid signed request was refused at the root broker during an upstream outage.
- A namespace-only reserved-port conflict refused a valid signed request. Removing the conflict did not make that refused operation ID replayable. The exact original reservation set was restored.
- Stopping only the independent observer produced unknown/unavailable evidence and refused a signed mutation; the observer was restored. Host memory was not deliberately exhausted; absolute/relative headroom refusals are offline tests.
- Agent mTLS refused a missing client certificate. A monitor certificate could read evidence but received 403 for mutation; a controller certificate with an unsigned body received 409. Unauthenticated operator incident access received 401.
- Eleven Prometheus targets healthy, all twelve gateway dashboard queries populated, nine alert rules validated, controller loop fresh and gateway idle at baseline. Expected fault alerts during injection are not normal-state health claims.
- Two constrained non-root runtime Pods: read-only images, all capabilities dropped, no service-account token and no node-delete permission. The broker remains a privileged trusted host component.
- Old idle descriptor/loopback fixture services were stopped/disabled and their unused namespace removed. Their historical evidence is retained [separately](fixture-validation-20261017.md); it is not counted as gateway recovery.

## Offline checks, archives and remaining limits

The subsequent [restart comparison](restart-comparison.md) on 18 October adds three alternating-order pairs and a separate final scope-qualification occurrence. Hard restart did not produce sustained recovery during the continuing load window in any pair; targeted repair did in all pairs. The new measurement suite has 76 passing offline checks. Final live acceptance again verified 11 healthy monitoring targets, all 12 dashboard queries and qualified automatic mode on the restarted process identity. Numeric-only results are in [restart-comparison.json](restart-comparison.json); detailed timelines and refreshed archives remain private on the laptop.

73 offline unittest checks passed, including consecutive diagnosis, mode persistence/refusal, distinct independent verification observations, scope/promotion/suspension, bounds, identity, fresh telemetry, root cooldown/refused-ID replay protection, journal recovery, compare-and-set rollback and administrator SSH input isolation. Python compilation, manifest rendering and JavaScript syntax checks passed. Mocked tests are not live fault results.

## Follow-up release acceptance — 18 October 2026

The canonical source rollout at `4de6b4a` (image `selfheal/platform:5d188a25bd316c2b`) preserved the gateway identity used in the comparison and returned healthy idle baseline. Live mTLS/monitoring and reserved-port, upstream-outage, refused-ID replay and missing-observer checks passed again. The root identity registry is outside the HAProxy-writable socket directory; a real FIFO registry was refused without blocking. Private post-rollout recovery archives were copied to the laptop and their checksum manifest and SQLite integrity verified. An administrator SSH stdin-consumption defect discovered during release checking was fixed with two additional regression tests; it does not change the gateway repair algorithm.

Detailed histories and private recovery archives are retained off-platform on the laptop. Archive readability/checksums and SQLite integrity are checked; these are not a full disaster-rebuild drill. The signed-in browser layout has not been visually revalidated; authenticated API workflows and delivered JavaScript syntax are verified.

Private-CA mTLS is implemented for agent/observer APIs. Enterprise IAM, independently authenticated reviewers, encrypted foundation telemetry, HA, automated certificate lifecycle, attested telemetry, fleet scalability, OKD qualification, production gateway/workload certification and DORA compliance remain outside this release. See [security](../docs/security.md) and [research](../docs/research.md).
