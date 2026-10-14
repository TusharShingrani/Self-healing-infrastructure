# Broader infrastructure: observed outcomes, 14 October 2026

The live lab now contains a real dependency chain: a non-root transaction on
app-1 resolves the dedicated DNS record on app-2, writes/reads an authenticated
Redis canary there, and writes/reads a local checkpoint. These are systemd
services on the existing Ubuntu VMs. nginx remains a separate experiment.

## Answers supported by the lab

1. **Repairable failures:** DNS record drift, a wrong cache memory budget,
   checkpoint permissions drift and a stopped Redis dependency were all repaired
   and independently verified. Earlier nginx experiments cover configuration,
   bounded logs and service state. This is evidence of selected cases, not all
   failures in those classes.
2. **Effective methods:** dependency transactions exposed failures even while
   the frontend process was running. Restarting that frontend did not recover
   any of the four initial failures. Bounded cause-directed recipes recovered
   all four. This is a mechanism comparison, not a randomised ranking of all
   methods or a diagnosis-accuracy benchmark.
3. **Learning:** each first unfamiliar pattern waited for a scripted
   investigation and approval. A separately applied second repair was verified
   and recorded. Explicit promotion allowed the third occurrence to repair
   automatically. Four procedures survived reopening the database and match the
   currently deployed contract. Gemini produced four real advisory responses;
   they remain unapproved advice and did not execute repairs.
4. **Impact:** the corrected stack completed 37,497 requests without a failure
   during a small concurrency/monitoring sweep. Cache authentication and canary
   administrative-command refusal were tested. Monitoring added measurable work;
   increasing request concurrency did not produce linear throughput scaling.
   No production availability, security assurance or fleet-scale claim follows.

See [research synthesis](../docs/research-synthesis.md) for 21 assessed source
entries, counterexamples to the old novelty claim and the reporting limits.

## Three learning occurrences for each failure

Operator roles are scripted. The manual occurrence executes the bounded recipe
outside the loop and records it afterwards. It is not an independent human
troubleshooting study. Times include the corresponding direct verification
pipeline. Different modes perform different numbers of checks, so their durations
must not be interpreted as a fair automated-versus-human speed comparison.
Waiting for real human approval was not measured.

| Fault | Approved repair and verification (s) | Recorded manual repair and verification (s) | Automatic repair and verification (s) | Verified recoveries |
| --- | ---: | ---: | ---: | ---: |
| dns_drift | 13.69 | 7.31 | 14.20 | 3/3 |
| cache_budget | 13.83 | 7.32 | 14.13 | 3/3 |
| permissions | 13.81 | 7.40 | 14.24 | 3/3 |
| cache_stop | 13.82 | 7.92 | 13.64 | 3/3 |

All four first-occurrence frontend restart comparators left the transaction
unhealthy. The final 12-run learning sequence took 571.7 seconds including
healthy intervals required by the real cooldown and action budget. Failure was
confirmed before every repair. These are three occurrences with different
workflow roles, not ten repetitions of each experimental configuration.

## Performance and request scalability

Each cell ran for twenty seconds. The active cells each contained two observed
monitoring ticks. Phase order was alternated for concurrency four. The old nginx
loop and external Prometheus probes remained active throughout: `off` means only
the new infrastructure loop was stopped. Results below are one exploratory
sweep, not repeated estimates of overhead.

| Request workers | New loop | Requests, all successful | Requests/s | p95 latency (ms) |
| ---: | --- | ---: | ---: | ---: |
| 1 | off | 6956 | 347.8 | 2.79 |
| 1 | on | 6867 | 343.0 | 3.26 |
| 4 | on | 6161 | 308.0 | 73.74 |
| 4 | off | 6484 | 323.2 | 73.48 |
| 8 | off | 5663 | 283.1 | 79.67 |
| 8 | on | 5366 | 267.4 | 80.70 |

The active Python monitor used about 0.036 to 0.039 CPU seconds during each
20-second phase. This excludes SSH child processes and remote/cloud/LLM work.
Observed healthy monitor cycle times during the sweep were about 1.5 to 2.6
seconds. A cause repair with multiple direct checks took about 14 seconds and
can exceed the ten-second polling interval. This serial prototype therefore
needs scheduling/parallelism work before scaling to many managed elements.
Request concurrency on two VMs is not a managed-node scalability experiment.
CPU quotas, network timing and the checkpoint critical section affect these
results; no single cause of the throughput changes was isolated.

## Findings retained rather than discarded

- The first installer checked Redis before its socket was ready. Startup waits
  now use bounded readiness checks.
- Redis protected mode correctly rejected the original unauthenticated client.
  We added generated host-local credentials and a canary account restricted to
  GET/SET/PING on `healer:*`. No password enters the repository or report.
- The first 720-request smoke sweep produced three failed requests. A bounded
  1,200-request reproduction found two failures specifically in checkpoint
  readback, while DNS and cache checks passed. Concurrent truncate/read was the
  cause. A process-local critical section fixed this single-service race. A test
  slows truncation deliberately; a repeated 720-request smoke sweep then passed.
- Changing the deployed transaction changed procedure scope. We preserved the
  original state and measurements, then repeated the complete learning sequence
  against the corrected workload. No old approval was silently inherited.
- A revoked recipe can no longer be promoted using successes from before its
  failure. Two new verified occurrences and review are required.

An additional automatic permissions recurrence verified the strengthened exact
owner/group and mode 0640 check. Functional recovery with mode 0777 is refused
by the verification test.

The original learning and smoke JSON are retained with `before-concurrency`
filenames, along with the actual failure diagnostics. These findings include a
bug in our synthetic workload and its manual software correction; the healer
was not claimed to invent that code patch automatically.

## Final checks and remaining boundaries

212 offline checks passed across safety, learning/advisor, adapter, host scripts,
operator, infrastructure and production-transaction suites. Both nginx health
endpoints are healthy. Four infrastructure procedures are validated; zero repair
incidents are pending. Ten Prometheus targets are up. The new eight-panel Grafana
dashboard was confirmed through its API. Known cloud, model and cache credentials
were scanned out of all changed source/evidence before publication.

The dashboard and metrics are read-only; operator decisions use authenticated
SSH. The healer retains broad SSH/sudo/cloud privilege, and the private cache
uses authenticated plaintext transport within the isolated lab. Command-specific
credentials, encrypted inter-service transport, adversarial-agent evaluation,
physical failures, durable data recovery, autoscaling and fleet-scale incident
coordination remain outside the demonstrated scope. The new workload primarily
proves learned recovery, not prevention; prevention needs an earlier warning and
an independently measured absence of failure.

## Traceable evidence

- `infrastructure-results.json`: final 12 runs, cases, procedures and audit.
- `infrastructure-benchmark.json`: sustained load, every request sample and security checks.
- `infrastructure-results-before-concurrency.json`: earlier learning contract.
- `infrastructure-benchmark-before-concurrency.json`: failed 720-request smoke sweep.
- `infrastructure-concurrency-failures.json`: exact faulty readback observations.
- `infrastructure-benchmark-smoke-after-concurrency.json`: corrected smoke sweep.
- `infrastructure-final-contract.json`: deployed scope, endpoints, targets and real model metadata.
- `infrastructure-tests.txt`: complete final test output.
