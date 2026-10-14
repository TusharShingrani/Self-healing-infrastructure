# Current design decisions

The authoritative deployed design is [the architecture](architecture.md).
Historical simulator and nginx A/B/C findings remain in [results](results.md);
their automatic-policy settings differ from the current reviewed service.

## Why use MAPE-K and adapters?

One loop coordinates observation, diagnosis, planning, bounded execution and
stored outcomes. VM-specific SSH/API behavior belongs to adapters. Nginx and
the dependency transaction share orchestration, but use different diagnosis
and verification contracts. Interface reuse does not mean those shared files
never change as requirements develop.

## Why a dependency transaction?

A working nginx unit cannot establish that DNS, cache writes and storage
permissions work. The synthetic transaction tests that chain and reports
individual dependency outcomes. Independent service and budget probes prevent
the transaction from masking wrong resource settings. Blocked measurements are
distinguished from independently failed probes.

## Why bounded recipes and human promotion?

Free-form shell learning would turn a diagnostic error into arbitrary privileged
execution. A recipe can only compose reviewed operations on named lab resources.
Unknown patterns need investigation. Two separately verified occurrences and
explicit promotion provide limited evidence for reuse; they do not establish a
statistical failure probability. More diverse repetitions remain necessary.

## What does learning establish?

The system remembers investigated failure patterns and validated repairs within
an identity/reference scope. It can reuse them automatically and revoke a failed
procedure. It does not train a model or independently invent unrestricted fixes.
Early-warning prevention is a separate historical experiment; faster repair
does not by itself prove prevention.

Learning and proactive mitigation already exist in published systems, including
Narya. This project's contribution is a bounded, reproducible EduCloud prototype
and measured workflow, not inventing learning-based self-healing. The
[research synthesis](research-synthesis.md) evaluates the literature directly.

## Why templates, bounded disks and off-platform evidence?

Fresh template deployment provides isolation and reproducibility. Two snapshot
slots do not limit the number of reverts. The baseline is plain Ubuntu, so
installers must recreate nginx, exporters and the dependency stack. A bounded
loop-backed log filesystem keeps injection away from root storage. The nginx
startup storage preflight is an explicit lab requirement, not stock behavior.
Cloud availability and retention are not guaranteed: keep code and raw results
off-platform, including failed trials rather than only successful demonstrations.

## Security and performance limits

Ownership checks, protected VM names, pinned SSH keys, bounded operations,
non-root services, limited Redis credentials and independent verification reduce
risk. Initial SSH trust is still trust on first use and internal HTTP/Redis is
not encrypted. Grafana does not approve actions; approval uses authenticated SSH.
The measured concurrency pilot covers a single transaction on two VMs and cannot
establish fleet scalability. The [audit](repository-audit.md) records further
fixes and current limitations rather than promising all code is defect-free.
