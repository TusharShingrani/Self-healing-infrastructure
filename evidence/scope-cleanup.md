> **Historical release evidence.** This file describes the earlier hashing workload or scope cleanup. It does not validate the bank-statement release. See [the current banking use case](../docs/focused-use-case.md).

# One-use-case cleanup — 15 October 2026

The supported project is Kubernetes background-job processing: a submitted
synthetic job must return the correct result within 30 seconds.

The earlier nginx and DNS/Redis/checkpoint demonstrations are retired. Their
two VM guests are stopped, with disks retained for recovery; they are no longer
part of the running system or active monitoring. Legacy controllers remain
disabled. Only the job-processing Grafana dashboard is provisioned and it is
the monitor's default dashboard. Historical Prometheus data is retained.

230 obsolete tracked files were archived locally before removal, including
old experiment launchers, installers, dashboards, reports and detailed results.
The shared investigation logic was preserved unchanged while the old DNS/Redis
managed element was removed. Shared controller, adapter/SSH safety and isolated
simulation tests remain because the job controller depends on them; they do
not launch an additional application. Generic VM-destruction allowlists are empty.

The README, architecture diagrams, deployment guide, literature-to-lab mapping,
working brief and console now describe the same job-processing use case.
Current literature answers distinguish procedural learning from prevention and
tested repairs from broader future possibilities.

## Verified after cleanup

- Seven required role VMs running; two obsolete demo VMs stopped.
- One project dashboard provisioned; 21 of 21 queries return data.
- Fourteen of fourteen active monitoring targets up, including host metrics
  for all seven required VMs. No legacy application probes remain.
- Eleven required infrastructure checks pass; a fresh independent job returns
  the correct result within its deadline.
- Three validated procedures remain eligible after controller restart.
- All 166 retained regression checks pass, along with shell syntax and Python
  compilation. Tests only for deleted legacy entry points were retired.
- Active documentation links resolve.

Detailed verification output, old source and experiment histories stay on the
operator laptop. This cleanup does not add a fault scenario, prove enterprise
readiness or turn integration trials into statistical research results.
