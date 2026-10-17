# Research argument and evidence boundaries

## Question 1: Which infrastructure failures can be self-healed?

Focus: reversible **resource-bound saturation**, with a known target, observable allocation failure and safe headroom. This implementation tests outbound local-port pressure and a process soft descriptor ceiling. Hardware failure, capacity without headroom, descriptor leaks, corruption, attack attribution and an unknown failure are not repaired by raising limits. A bounded limit increase buys capacity; it does not remove every underlying cause.

The [Linux IP sysctl documentation](https://www.kernel.org/doc/html/latest/networking/ip-sysctl.html) describes port-range/reserved-port behaviour and cautions about socket reuse tuning. Incoming accepts do not require a fresh ephemeral local port each. Therefore the network experiment tests outbound allocation and does not blindly change `tcp_tw_reuse`. The [prlimit manual](https://man7.org/linux/man-pages/man2/prlimit.2.html) establishes soft/hard resource limits and privilege requirements; the lab never raises its approved hard ceiling.

## Question 2: Which detection and repair methods are effective?

The hypothesis is that **correlated symptoms plus bounded runtime adaptation** can restore useful infrastructure operations without restarting the affected process. Occupancy alone cannot establish a failure. Counters must increase between fresh observations of the same identity; the workload must fail its required allocations. After action, measure actual allocations/a fresh network transaction, not merely a changed configuration value.

Compare observe-only baseline, operator-approved adaptation and reviewed automatic reuse. Record time to diagnosis/decision/recovery, failed and successful allocations, target identity, controller overhead and rollback result. The first live four-occurrence protocol demonstrates mechanism feasibility, not statistical superiority. A larger repeated, randomized comparison is needed for claims about effectiveness or prevention.

Storage is capability-gated. [K3s documents SQLite as the default](https://docs.k3s.io/datastore); the discovered single-server lab uses SQLite, so etcd WAL metrics cannot represent this control plane. [ionice](https://man7.org/linux/man-pages/man1/ionice.1.html) changes scheduling priority, not available capacity. Until a scheduler-specific controlled comparison proves benefit and a safe target is integrated, storage remains observation/investigation, not autonomous remediation.

## Question 3: How can the system learn from past failures?

[IBM's autonomic manager description](https://www.redbooks.ibm.com/redbooks/pdfs/sg246665.pdf) places shared knowledge beside Monitor, Analyse, Plan and Execute. Here Knowledge persists incident evidence, approvals, outcomes and procedure scope. Two separately observed verified incidents are a qualification threshold, not statistical confidence. A human explicitly promotes reuse; a future identical scoped signature may then execute automatically. Failed verification suspends it. Identity/policy change prevents reuse.

This is transparent case/procedure learning. It neither trains a model nor invents arbitrary shell commands. It reduces repeated manual decisions for a validated case. Prevention before an actual allocation failure is a separate future hypothesis; the current signature is reactive and must not be reported as predictive prevention.

## Question 4: Reliability, security, performance and scalability

Reliability benefit is tested as recovered useful operations with unchanged process identity. Expiring leases and a durable journal limit persistent unintended tuning; deferred/conflicted rollback still needs an operator. Security requires protecting the privileged broker and signing keys. Raising resource limits can increase memory pressure or mask a leak. Performance effects and agent overhead require measurement; one-node evidence cannot establish fleet scalability. The DaemonSet separates node-specific effects, but the single controller/PVC is not a highly available design.

## Banking governance context: DORA

The following is an engineering mapping, not legal certification. [DORA, Regulation (EU) 2022/2554](https://eur-lex.europa.eu/eli/reg/2022/2554/oj/eng) provides the context:

| Provision | Project evidence or design response |
|---|---|
| Article 9, protection/prevention | Least privilege, bounded changes and explicit trust boundaries |
| Article 10, detection | Fresh correlated resource measurements; unavailable evidence remains unknown |
| Articles 11–12, response/recovery and backups | Reviewed runbooks, lease rollback and private off-platform recovery state |
| Article 13, learning/evolving | Incident review, verified procedural reuse and suspension after failure |
| Articles 24–25, testing | Isolated failure injection, outcome checks and retained experiment records |

These controls cover only a small technical slice. Governance, critical-function assessment, reporting/classification, enterprise IAM, supplier controls, resilience programme and regulatory obligations remain outside this lab. A successful demo does not demonstrate compliance.

## Reproducibility and ethics

Use dedicated owned fixtures, fixed bounds and deadlines. No public port scans, real customer information or production control-plane stress. Retain detailed output privately; publish source and anonymised numeric results only. Old bank application tests are historical evidence for a different system and cannot validate this implementation.
