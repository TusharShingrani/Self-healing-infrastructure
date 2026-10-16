> **Historical release evidence.** This file describes the earlier hashing workload or scope cleanup. It does not validate the bank-statement release. See [the current banking use case](../docs/focused-use-case.md).

# Live job-service validation â€” 15 October 2026



The current deployment is Kubernetes job processing backed by PostgreSQL,

with a separate independent client, operator console and MAPE-K controller.

Nine VMs remain allocated; the two older app VMs are historical fixtures.

The older nginx and infrastructure controllers are stopped and disabled.

Their monitoring series remain historical; their inactive scrape jobs were removed.



## Observed outcomes



263 regression checks passed on the deployed Ubuntu release (full Linux log

included). Nine controlled core occurrences completed with independent fresh

job results and cause-specific checks. The operator roles in these trials were

scripted; this is not a human usability study.



| Fault | Investigator-approved | Recorded human repair | Promoted automatic reuse |

|---|---:|---:|---:|

| Database endpoint configuration | 20.62 s | 16.63 s | 20.47 s |

| Desired workers set to zero | 90.22 s | 91.58 s | 95.24 s |

| Worker memory configuration | 23.66 s | 20.18 s | 19.94 s |



Times run from injection to verified repair, including verification and normal

cooldowns. They are not all downtime. Kubernetes retained healthy old Pods

while the endpoint and memory rollout was invalid: those two scenarios

preserved job availability. Desired workers zero caused a real deadline

failure. No healthy old Pods were killed to manufacture an outage.



Two distinct verified repairs plus explicit promotion produced three

current-scope procedures. The third occurrence reused each automatically.

After restarting the controller all three remained eligible. This demonstrates

bounded procedural learning, not model training or arbitrary new repair synthesis.



With the healer observe-only, Kubernetes replaced one deliberately deleted

stateless worker Pod and verified fresh work in 33.61 seconds. This is a

different fault from desired replicas zero, so the timings are not a

head-to-head comparison of Kubernetes and the healer.



A supporting private network-policy fault permitted only the owned monitor

endpoint. An independent witness detected the undesired connection. Unknown

incident 28 required investigation; incident 29 was approved through the live

browser console. The engine repaired the policy and independently verified

that database access remained allowed, monitor access was denied and a new

job completed correctly. This single verified security repair was not promoted.

The console uses an inline decision review rather than a native browser popup.



Real Gemini advice was received, but suggestions included an inappropriate

configuration recipe for a memory-limit incident and an overly broad network

repair suggestion. Advice remained non-executable. Evidence and the reviewed

procedure catalogue determined the selected action; no diagnosis accuracy

claim follows from these examples.



## Final operational check



All 11 required checks passed, fresh work completed correctly, all 19 active

Prometheus targets were up, the controller was unpaused and both controller

and console services were active. All 21 job dashboard queries returned data.

Three validated current-scope procedures survived controller restart.

See jobs-final-status.json, jobs-live-summary.json, jobs-native-pod-recovery.json,

console-live-validation.json and jobs-monitoring-query-validation.json.

Full histories are gzip archives with uncompressed hashes in

jobs-evidence-manifest.json. Failed protocol and pilot outputs are retained.

Actual executed source hashes are recorded separately: live trial driver/UI

fixes were working-tree changes on parent commit 636d933, later published

with this evidence. Do not describe the unmodified parent as the exact trial source.



## Limitations and recovery



Three occurrences per core fault are integration evidence, not the planned

10-run-per-fault statistical evaluation. The first live protocol failed because

it assumed a rollout necessarily caused an outage; its failure is preserved.

Security repair has one verified occurrence. Untested failures remain unproven.

The console is single-operator, private and loopback-only. Token renewal,

enterprise identity, multi-tenancy and high availability are not implemented.

Kubernetes credentials expire after their issued lifetime; never fall back to

cluster-admin on expiry. Cloud credentials currently reside in the user service

manager; a host restart requires restoring them through the private runbook.



Private pre-change backup includes keys and a PostgreSQL dump; archive members

were fully read for integrity, but database restoration was not tested here.

A separate consistent SQLite backup preserves the final learned procedures on

the laptop. Neither archive nor credentials are committed. The isolated lab

can still be reclaimed by the platform; source alone does not restore job data.


## Subsequent scope cleanup

The counts above record the original validation point. The later cleanup
stopped the two old demo VMs, removed legacy monitoring and dashboards, and
retired obsolete source and reports to a local archive. The current setup has
seven running role VMs, one provisioned dashboard and 14 active scrape targets.
All 11 health checks, 21 dashboard queries and 166 retained regression checks
passed after cleanup; all three learned procedures remained eligible. See
[the cleanup record](scope-cleanup.md). Detailed histories remain local by the
user's explicit choice, not pending publication approval.
