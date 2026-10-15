# Self-healing Kubernetes job processing with MAPE-K

One use case: **a submitted job must finish correctly within 30 seconds**.
This research prototype investigates failures that prevent useful work,
asks an operator to approve a bounded repair, verifies a fresh job from another
machine, and remembers reviewed procedures for recurring incidents.

**The thing being self-healed is the job-processing service.** Think of a
company submitting background work such as report generation: accepting the
request is insufficient; a worker must finish it and return the right result.
This lab uses synthetic SHA-256 jobs so correctness can be checked exactly.

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
- [Verified live results and limits](evidence/jobs-live-report.md)
- [Scope cleanup and current checks](evidence/scope-cleanup.md)

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

Live deployment was verified on 15 October 2026: 263 regression checks passed
before retirement; the focused suite now passes all 166 retained checks.
Nine core repair trials verified, browser approval restored network isolation,
and Kubernetes replaced a worker Pod with the healer observe-only. After scope cleanup all 11 required checks and 14 active monitoring targets
pass; the earlier 19-target count included the retired demos.
Three validated procedures survived a controller restart. See the
[live results and limitations](evidence/jobs-live-report.md).

The two configuration rollout faults preserved job availability; their repair
times are not downtime measurements. The worker-capacity fault did breach the
job deadline. These are integration trials, not a statistical benchmark.

Another application needs its own contract, probes, bounded repairs and tests.
Enterprise identity, multi-tenancy, high availability and universal plug-and-play
are future work; this lab does not establish enterprise readiness.

## Only this use case is active

The old nginx, DNS/Redis and checkpoint demonstrations have been retired.
Their two VMs are stopped, their dashboards and probes are removed from active
monitoring, and their scripts, reports and historical data are archived on the
operator laptop. They are not part of this project's supported deployment.

Seven running VMs support one application: healer, monitoring, Kubernetes
control, two Kubernetes workers, PostgreSQL and the independent checker.
Multiple Pods are replicas or supporting checks, not separate project use cases.
The repository retains shared engine, transport and isolated simulation safety
tests because they protect the job-service controller; no legacy demo launcher
or legacy application installer remains.
