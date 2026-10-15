# Project working brief

ONE use case: keep a Kubernetes background-job service completing correct
results within 30 seconds. Read README.md, docs/focused-use-case.md,
docs/architecture.md, docs/jobs-deployment.md and docs/web-console.md.

Seven VMs are active: healer, monitor, Kubernetes control, two workers,
PostgreSQL, independent checker. Old app-1/app-2 are stopped with disks retained;
old nginx/DNS/Redis/checkpoint experiments are archived on the laptop. Do not
restart or reintroduce them. Do not expand the fault catalogue without a scoped
research reason. Never delete detailed experiment histories or upload them;
the user explicitly chose to keep them on the laptop.

The job controller and console run from ~/projects/job-service-console.
Core scenarios: database endpoint, worker desired replicas, worker memory
settings. Network-policy drift is a supporting security misuse case within
this same application. Kubernetes owns Pod lifecycle. The healer owns reviewed
configuration correction, evidence, operator decisions, verification and memory.

Unknowns require investigation. AI advice is non-executable. Two independently
verified occurrences plus promotion allow scoped recurring repair. Preserve
state/jobs and state/expansion.json, pinned host keys and private credentials.
Changes to mapek/jobs.py, mapek/kubernetes.py or tools/job-host/probe.py affect
procedure scope; revalidate deliberately. Do not change these just to rename
shared modules. mapek/infrastructure.py now contains shared investigation only.
mapek/educloud.py supplies pinned transport; its generic destructive allowlist
in config/lab.json is empty. No healer/database destruction is authorized.

Run bash tools/test_all.sh and verify fresh independent jobs, all 11 checks,
active monitor targets and the single provisioned Grafana dashboard after
changes. Historical 263-check total predates retirement; report current counts
separately. Nine live core occurrences are integration trials, not a statistical
benchmark. Endpoint/memory rolling updates preserved availability; only worker
capacity zero breached the deadline. See evidence/jobs-live-report.md.

Credentials stay outside Git. User service-manager credentials need restoring
privately after host reboot; Kubernetes token renewal is not automated. Console
is single-operator loopback-only; enterprise readiness is not established.
