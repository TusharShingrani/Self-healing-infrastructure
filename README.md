# MAPE-K self-healing for a fictional bank statement service

**A customer requests their monthly account statement. The system must deliver the correct statement, without losing an accepted request or exposing another account.** This is the single use case.

The application runs as API and worker containers in Kubernetes, with PostgreSQL holding a synthetic ledger and durable statement requests. The healer repairs reviewed infrastructure configuration: the database connection endpoint, missing worker capacity and unsuitable worker memory settings. It never edits ledger entries or “fixes” a balance. There are no payments, real customers or real financial data.

## Understand the system

- [Business use case and exact service requirements](docs/focused-use-case.md)
- [Architecture, diagrams and MAPE-K responsibilities](docs/architecture.md)
- [Banking practices, DORA mapping and production gaps](docs/dora-control-mapping.md)
- [Research questions and literature](docs/research-synthesis.md)
- [Operator console](docs/web-console.md) and [demo-video walkthrough](docs/demo-video.md)
- [Deployment and recovery](docs/jobs-deployment.md)

## What you see

The private console has three views: **Request a statement**, **Follow the self-healer**, and **Inspect learned memory**. Requesting a statement exercises the real API, database and worker. The operations view explains failing checks, evidence, investigation, approval and verification. The memory view shows reviewed procedures and lets the operator suspend automatic reuse. Grafana provides the detailed monitoring timeline.

MAPE-K means: monitor customer outcomes and infrastructure; analyse the evidence; plan a bounded cause-directed repair; execute an approved or previously validated procedure; retain its evidence and outcome in Knowledge. Unknown failures require investigation. AI advice cannot execute commands. Two distinct verified incidents and explicit promotion are required before scoped automatic reuse. This is procedural learning, not retraining a model or learning arbitrary shell commands.

## Banking safeguards

Amounts use integer cents. Each request has account-scoped idempotency. Account identity comes from its credential. A separately pinned fixture checks exact ledger entries, balances and statement hash. API and database connections validate TLS identities. Separate database roles cannot rewrite the ledger; completed statements and audit records are protected from application mutation. Repairs must pass fresh independent end-to-end checks. A known integrity failure blocks automatic repairs.

These are **DORA-informed prototype controls**, not a claim of DORA compliance or production banking readiness. The lab has single points of failure, a single operator, manual credential renewal and limited backup frequency. See the explicit [control gaps](docs/dora-control-mapping.md).

## Verification

Run `bash tools/test_all.sh` on the healer. The live acceptance suite is `python3 tools/lab_shell.py python3 tools/test_bank_live.py --controlled-experiment`; it creates synthetic requests and restores a backup into a separate scratch database. Never use a production database for this exercise.

On 16 October 2026 all 16 live banking acceptance checks passed. Repeated repair experiments are documented separately when completed. Earlier hashing/nginx results do not validate this banking release. Detailed histories, credentials and private deployment references stay off GitHub.

Seven VMs support this one service: healer, monitoring, Kubernetes control, two Kubernetes workers, PostgreSQL and an independent checker. The old application VMs remain stopped. Stable internal names such as `jobs-lab`, `job-api` and `state/jobs` are implementation identifiers, not additional applications.
