# Research argument and evidence boundaries

## Optional AI-assisted investigation

The [advisory workflow](ai-investigation.md) extends investigation of the same gateway rather than adding unrelated applications. The research question is whether evidence-constrained model advice improves investigation over deterministic classifications, measured by correct hypotheses, unsupported claims, useful next checks, unsafe advice, latency and operator corrections. The deterministic controller remains the authority for qualified repair. Provider integration success does not establish diagnostic effectiveness; new fault classes remain unqualified until independently tested. Human repair records are explicit operator reports and do not count as verified automatic learning.

The [repeated provider study](../evidence/diagnosis-quality.md) ran three calls on each of seven constructed cases before and after guidance refinement: 42 schema-valid reports. Strict complete-report rubric compliance improved from two to six cases, while the same-input checklist classified all seven known cases correctly. Residual stale-data wording and verification errors remain. This single involved evaluator's in-sample result supports bounded advisory use and independent safety controls, not superior open-world diagnosis or measured human-time savings.

## Question 1: Which infrastructure failures can be self-healed?

Focus: reversible **resource-bound saturation**, with a known target, observable allocation failure and safe headroom. The primary implementation tests a real HAProxy gateway's outbound local-port exhaustion. Earlier port/descriptor fixtures remain regression evidence. Hardware failure, capacity without headroom, descriptor leaks, corruption, attack attribution and an unknown failure are not repaired by raising limits. A bounded limit increase buys capacity; it does not remove every underlying cause.

The [Linux IP sysctl documentation](https://www.kernel.org/doc/html/latest/networking/ip-sysctl.html) describes port-range/reserved-port behaviour and cautions about socket reuse tuning. Incoming accepts do not require a fresh ephemeral local port each. Therefore the network experiment tests outbound allocation and does not blindly change `tcp_tw_reuse`. The [prlimit manual](https://man7.org/linux/man-pages/man2/prlimit.2.html) establishes soft/hard resource limits and privilege requirements; the lab never raises its approved hard ceiling.

## Question 2: Which detection and repair methods are effective?

The hypothesis is that **correlated symptoms plus bounded runtime adaptation** can restore useful infrastructure operations without restarting the affected process. Occupancy alone cannot establish a failure. Counters must increase between fresh observations of the same identity; the workload must fail its required allocations. After action, measure actual allocations/a fresh network transaction, not merely a changed configuration value.

The gateway study compares observe-only baseline, operator-approved adaptation and reviewed automatic reuse with the same bounded 24-second load and seeded trial order. An independent VM sends nonce-checked HTTP requests through real HAProxy; it measures failed checks and time from first failure to three consecutive successes while background load continues. Two qualification trials precede three comparisons per mode. Reviewed approval after two seconds is scripted laboratory protocol, not measured human response time. This small comparison supports feasibility in this environment, not general statistical superiority, capacity or prevention claims. Detailed evidence stays private; see the public [validation record](../evidence/validation.md).

One seeded ordering is not a balanced crossover study. Trials drain and restore the range and require a successful allocation/client check, but remaining socket TIME_WAIT and environmental variation can differ. More repetitions, balanced order, multiple workloads and independent deployments would be needed to estimate general treatment effects or scalability.

The subsequent [hard-restart comparison](../evidence/restart-comparison.md) adds the missing simpler recovery baseline. Three alternating-order pairs used the same continuing 24-second/64-worker load and the same diagnosis trigger. Hard restart recovered sustainably in 0/3 trials, with 32 pre-action pending test requests interrupted per trial; targeted repair recovered in 3/3 with a median 4.213 seconds after the trigger and zero such transport interruptions. These measurements support the targeted action for this constraint. They establish neither a universal advantage over restarting, financial loss, nor the necessity of a full healer instead of correct static capacity configuration. Graceful reload and HA failover were not tested.

The [HAProxy 2.8 management guide](https://docs.haproxy.org/2.8/management.html) documents runtime statistics and outgoing-connection behaviour. Its backend connection-error counter is not a precise Linux errno. The diagnosis therefore also requires a separate actual namespace allocation probe returning EADDRNOTAVAIL, high occupancy, fresh client/gateway failures and a healthy independently checked upstream. The installed Ubuntu package version and documentation series are recorded separately; the online 2.8 manual may have a newer patch version.

Storage is capability-gated. [K3s documents SQLite as the default](https://docs.k3s.io/datastore); the discovered single-server lab uses SQLite, so etcd WAL metrics cannot represent this control plane. [ionice](https://man7.org/linux/man-pages/man1/ionice.1.html) changes scheduling priority, not available capacity. Until a scheduler-specific controlled comparison proves benefit and a safe target is integrated, storage remains observation/investigation, not autonomous remediation.

## Question 3: How can the system learn from past failures?

[IBM's autonomic manager description](https://www.redbooks.ibm.com/redbooks/pdfs/sg246665.pdf) places shared knowledge beside Monitor, Analyse, Plan and Execute. Here Knowledge persists incident evidence, approvals, outcomes and procedure scope. Two separately observed verified incidents after the last failure in the exact scope are a qualification threshold, not statistical confidence. A human explicitly promotes reuse; a future identical scoped signature may then execute automatically. Failed verification suspends it. Identity/policy change prevents reuse.

This is transparent case/procedure learning. It neither trains a model nor invents arbitrary shell commands. It reduces repeated manual decisions for a validated case. Prevention before an actual allocation failure is a separate future hypothesis; the current signature is reactive and must not be reported as predictive prevention.

## Question 4: Reliability, security, performance and scalability

Reliability benefit is tested as recovered independent client transactions with unchanged gateway identity. Expiring leases and a durable journal limit persistent unintended tuning; deferred/conflicted rollback still needs an operator. Security includes private-CA mTLS, separate read-only monitor identity, signed effects and a root-owned admission policy. Raising resource limits can increase memory pressure or mask a leak; gateway admission checks both absolute and proportional host memory and reserved-port conflicts. Refusal tests avoid deliberately exhausting a shared host's memory. Performance effects and agent overhead require measurement; one-node evidence cannot establish fleet scalability. The DaemonSet separates node-specific effects, but the single controller/PVC is not a highly available design.

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
