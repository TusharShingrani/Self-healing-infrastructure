# Current project brief

ONE use case: fictional bank monthly account-statement generation. Read README.md, docs/focused-use-case.md, docs/architecture.md, docs/dora-control-mapping.md and docs/demo-video.md.

The live release is ~/projects/bank-statements. Seven VMs support API/worker containers in Kubernetes, PostgreSQL, an independent checker, monitoring and the healer. Old app VMs stay stopped. Stable jobs-lab/job-api/state/jobs names are internal identifiers, not separate business services.

Never change ledger facts, delete accepted requests or rewrite completed statements to restore health. Unknown/integrity failures require investigation. AI is advisory and receives a restricted observation projection. Fixed reviewed configuration recipes alone may be promoted after two distinct verified occurrences; database/network/compute remain approval-only. Preserve Knowledge and procedure scope. Changing mapek/jobs.py, mapek/kubernetes.py or tools/job-host/probe.py invalidates scope and requires deliberate revalidation.

Credentials, generated deployment references, PKI keys, raw histories and detailed evidence remain private. The user explicitly declined publication of histories. Do not destroy protected VMs or restart retired services. Run tools/test_all.sh and verify independent banking checks after changes. DORA-informed PoC does not mean DORA compliant or production ready. Consult current evidence rather than historical nginx/hashing test counts.
