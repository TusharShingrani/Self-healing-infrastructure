# Self-healing Kubernetes job processing with MAPE-K

One use case: **a submitted job must finish correctly within 30 seconds**.
This research prototype investigates failures that prevent useful work,
asks an operator to approve a bounded repair, verifies a fresh job from another
machine, and remembers reviewed procedures for recurring incidents.

The application is an API and worker service running in Kubernetes, backed by
PostgreSQL. Synthetic SHA-256 jobs provide independently checkable results.
The main faults are a wrong database endpoint, missing worker capacity and
unsuitable worker memory settings. Network-policy drift tests security within
the same application. Kubernetes handles ordinary Pod restarts; the healer
handles reviewed application requirements that a restart alone cannot fix.

## Start here

- [Use case, assessor scope and evaluation](docs/focused-use-case.md)
- [Architecture and responsibilities](docs/architecture.md)
- [Operator web console and access](docs/web-console.md)
- [Ordered lab deployment and evaluation](docs/jobs-deployment.md)
- [Literature, research questions and limitations](docs/research-synthesis.md)
- [Pilot findings and evidence boundary](evidence/jobs-pilot-notes.md)

## Operator interface

The private console provides an application overview, required health checks,
incident evidence and AI advice, investigate/approve/reject controls, verified
manual repair recording, procedure promotion and an audit trail. It links to
the job-service Grafana dashboard. Stale evidence is never shown as healthy.

```sh
python3 tools/console.py --set-password
bash tools/start_console.sh start
```

Use an SSH tunnel and open `http://127.0.0.1:8085`; see the
[console runbook](docs/web-console.md). It is loopback only and has a separate
password. Cloud credentials never enter a browser form. The first release
selects approved configuration repairs; contract changes remain reviewed
repository changes rather than arbitrary browser edits.

## What learns

Knowledge stores investigated causes, reviewed actions and verified outcomes.
Two distinct verified occurrences and explicit promotion allow reuse only
within the matching resource, reference, adapter and recipe scope. Changed
scope requires revalidation; failed reuse revokes eligibility. The LLM offers
advice but cannot invent executable capabilities. This is procedural learning,
not model training or general prevention of unknown faults.

## Verification status

```sh
bash tools/test_all.sh
```

Live deployment was verified on 15 October 2026: 263 regression checks passed,
nine core repair trials verified, browser approval restored network isolation,
and Kubernetes replaced a worker Pod with the healer observe-only. All 11
required checks and 19 active monitoring targets passed the final check.
Three validated procedures survived a controller restart. See the
[live results and limitations](evidence/jobs-live-report.md).

The two configuration rollout faults preserved job availability; their repair
times are not downtime measurements. The worker-capacity fault did breach the
job deadline. These are integration trials, not a statistical benchmark.

Another application needs its own contract, probes, bounded repairs and tests.
Enterprise identity, multi-tenancy, high availability and universal plug-and-play
are future work; this lab does not establish enterprise readiness.

## Earlier experiments

The nginx and DNS/Redis work remains historical evidence and regression
fixtures. See [earlier architecture](docs/legacy-architecture.md),
[earlier README](docs/legacy-readme.md) and [nginx results](docs/results.md).
Retire legacy automatic controllers only after backup and a successful live
job-service check. Do not erase evidence or destroy machines for presentation.
