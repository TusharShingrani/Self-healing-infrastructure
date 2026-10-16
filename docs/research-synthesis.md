# Research synthesis: self-healing infrastructure

The literature covers a broader field than the implemented prototype. The
current empirical scope is ONE fictional bank statement-generation application; see
[the focused use case](focused-use-case.md). Earlier nginx and dependency
results are historical evidence, not validation of the new adapter.


Research updated: 16 October 2026. This is a structured literature review and an
engineering evaluation plan, not a systematic review claiming exhaustive coverage.
Current live findings are in [the banking control mapping](dora-control-mapping.md).
Historical experiments are archived locally and excluded from current claims.

## Method and evidence quality

Searches combined self-healing, autonomic computing, MAPE-K, failure detection,
root cause analysis, adaptive mitigation, gray failures, chaos evaluation and
AIOps agents. Searches targeted USENIX proceedings, original research papers,
author publications and official project documentation. Inclusion required a
directly relevant mechanism, empirical evaluation or operational specification.
Search-engine summaries and practitioner reposts were not used as independent
evidence. Primary publication pages and available full papers were read, including
evaluation and limitations sections. Links and interpretation appear below.

The evidence has different strengths. Production studies support feasibility in
their own environments. Controlled experiments support a particular mechanism.
Official documentation explains product behaviour but does not establish that
it is the most effective method. Our small lab can establish reproducible
examples, not cloud-scale effectiveness or universal detection accuracy.

| Source | Evidence and limitation | Decision for this project |
| --- | --- | --- |
| [Kephart, research challenges of autonomic computing, 2005](https://research.ibm.com/publications/research-challenges-of-autonomic-computing--1) | Foundational research framing. Human objectives still govern autonomic management. Not an empirical guarantee of autonomy. | Keep explicit objectives and a distinction between manager and managed system. |
| [Candea et al., Microreboot, OSDI 2004](https://www.usenix.org/legacy/events/osdi04/tech/full_papers/candea/candea_html/index.html) | Auction-system experiments found substantial benefits from restarting small components. State separation is a prerequisite. | Keep restart as one mitigation, with smaller scope than a VM reboot. Do not present it as a universal cause repair. |
| [Yuan et al., OSDI 2014](https://www.usenix.org/conference/osdi14/technical-sessions/presentation/yuan) | Analysis of 198 failures in five distributed data systems. Many failures could be reproduced on very few nodes; error-handling tests mattered. | A small dependency lab is meaningful. Test failure paths, not only healthy behaviour. |
| [Li and Huang, Gray Failure, SREcon 2024](https://www.usenix.org/conference/srecon24americas/presentation/li) | Operational presentation explaining differential observability. A talk, not a new controlled benchmark. | Compare process state with actual client transactions. |
| [Levy et al., Narya, OSDI 2020](https://www.usenix.org/system/files/osdi20-levy.pdf) | Production prediction, experiments and bandit action selection. Reported 26% fewer VM interruptions against its previous static strategy. Different scale and privileges from this lab. | Learning already exists in the literature. Learn from measured outcomes; do not claim our case memory is reinforcement learning. |
| [Li et al., Gandalf, NSDI 2020](https://www.usenix.org/conference/nsdi20/presentation/li) | Production rollout correlation and assessment. Strong results for its deployment domain, not all incidents. | Record configuration identity and component context before diagnosing or reusing a repair. |
| [Huang et al., Metastable Failures, OSDI 2022](https://www.usenix.org/system/files/osdi22-huang-lexiang.pdf) | Study of incident reports and modelling. Amplification can sustain an outage after the trigger ends. Reports have incomplete evidence. | A restart may not remove a sustaining cause. Bound load and retries; do not inject uncontrolled resource exhaustion. |
| [Malik et al., CHESS, 2023 manuscript](https://arxiv.org/html/2303.07283v1) | Reusable chaos evaluation artifact with two microservice case studies. Not proof of general autonomous recovery. | Define steady state, confirm injection, measure recovery and restore the environment. |
| [AIOpsLab, 2025 manuscript](https://arxiv.org/html/2501.06706v1) | End-to-end benchmark separates detection, localisation, diagnosis and mitigation. Its best evaluated agent reached 59.32% overall accuracy in the reported setting. | Measure these tasks separately. Keep an LLM advisory; fluent explanations are not evidence of a working repair. |
| [Benecchi et al., Verify, Augment, Improve, SEAMS 2026](https://publikationen.bibliothek.kit.edu/1000196013) | Ground-truth verification of ineffective adaptations drives data augmentation and surrogate retraining. Cyber-physical benchmarks, not this cloud lab. Primary repository abstract inspected; publisher PDF retrieval timed out. | Learning from mistakes is established research. Revoke failed procedures and investigate them; do not claim our recipe memory retrains a model. |
| [Wiesinger et al., SEAMS 2026](https://conf.researchr.org/details/seams-2026/seams-2026-research-track/22/Leveraging-Low-Parameter-LLMs-for-Self-Healing-in-Kubernetes-Based-Container-Orchestr) | Conference abstract reports prompt chaining and iterative feedback on 15 faults. Its 96.67% result cannot be compared directly with AIOpsLab's different benchmark. Full evaluation was not retrieved. | Separate diagnosis from execution and verify through the actual environment. No justification for assuming our Gemini advisor has that accuracy. |
| [Pasquini et al., USENIX Security 2026](https://www.usenix.org/conference/usenixsecurity26/presentation/pasquini) | Original telemetry-manipulation attack study and structured sanitisation defence. Its threat model includes externally influenced telemetry. | Never let log text create executable capabilities or grant approvals. Our allowlist is one control, not an evaluated reproduction of their defence. |
| [PASE, July 2026 preprint](https://arxiv.org/html/2607.01595v1) | Proposes plan generation and neural-symbolic world-model checks. Model-based safety depends on model fidelity; peer-review status not established here. | Treat predictive plan checks as research context, not as a substitute for ownership and independent live verification. |
| [IFSHM, June 2025 preprint](https://arxiv.org/html/2506.07411v1) | Combines semantic LLM interpretation and reinforcement-learning action selection. Preprint claims need independent reproduction. | Reinforcement learning requires data and evaluation beyond the current lab; do not rename case memory as DRL. |
| [Google SRE, monitoring](https://sre.google/sre-book/monitoring-distributed-systems/) | Operational guidance covering user-visible and internal signals. Not a comparison trial. | Use latency, errors and saturation alongside component state. |
| [Google SRE, automation](https://sre.google/sre-book/automation-at-google/) | Operational experience includes the hazards of automation at scale. | Keep ownership, bounded effects, verification and a human fallback. |
| [Google SRE, overload](https://sre.google/sre-book/handling-overload/) | Guidance on capacity and graceful degradation. Workload cost varies. | Measure request latency and resource consumption, not only requests per second. |
| [Kubernetes probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/) | Official distinction between startup, readiness and liveness. Incorrect probes can cause harmful restarts. | Process liveness and transaction readiness are separate observations even without containers. |
| [Redis eviction](https://redis.io/docs/latest/develop/reference/eviction/) | Official maxmemory and noeviction semantics. | Make memory-limit failure an actual refused write, not a simulated service stop. |
| [Redis security](https://redis.io/docs/latest/operate/oss_and_stack/management/security/) | Official access and trusted-network guidance. Private addresses alone are insufficient for production protection. | Authenticate the disposable cache and restrict its canary client; document remaining operator privilege limits. |
| [Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html) | Official resource-controller semantics. Resource limits constrain impact; they do not repair software bugs. | Cap service memory, CPU and task counts during lab experiments. |

## 1. Which infrastructure failures can be self-healed?

A useful boundary is observable evidence, a permitted repair, an approved desired
state and a trustworthy outcome check. Detectability alone is insufficient.
For this application the evaluated failures are database endpoint drift, desired
worker capacity zero and wrong worker memory specifications. Private network
policy drift is a supporting misuse case. Native Kubernetes Pod replacement
is a separate baseline, not a healer accomplishment. Database corruption,
compromise, arbitrary network faults and unknown software bugs are outside the
automatic catalogue. Unknown incidents require investigation.

## 2. Which methods are most effective for detection and repair?

No universal winner follows from the literature. This lab combines independent
statement submission/reconciliation checks with Kubernetes state and approved invariants.
A Pod being alive does not establish correct work. Kubernetes reconciles the
configured state; a wrong configured database address or memory limit persists
across restarts. A bounded cause-directed configuration repair is therefore
needed. Fresh independent work plus cause-specific checks establish success.
See the source catalogue above for probes, gray failures, contextual diagnosis
and verification research; their reported numbers do not transfer to this lab.

The earlier nine-occurrence hashing workload demonstrated the control integration but is historical evidence. The banking release uses its own exact statement oracle, live acceptance tests and new repeat trials. Report those results separately; neither a successful configuration command nor an old workload result proves banking recovery.

## 3. How can a system learn from past failures to prevent them?

The system stores investigated causes, reviewed actions and independently
verified outcomes. Two distinct verified occurrences and explicit promotion
permit matching automatic reuse. Resource identity, approved references,
adapter and recipe scope must match; failed reuse revokes eligibility. Historical hashing procedures were reused across a restart; banking procedures require their own scope and fresh validation.
This is procedural learning, not LLM training or general repair synthesis.

Recovery from a repeated fault is not proof of prevention. No current experiment
establishes prediction of a novel failure before its onset. Earlier Gemini advice included inappropriate suggestions; it remained advisory and is not evidence of a correct banking diagnosis. Human notes cannot
be executed, and a genuinely new capability requires code review and validation.
The source catalogue discusses production learning systems and research
alternatives; this prototype makes no novelty claim over those systems.

## 4. How does self-healing affect reliability, security, performance and scalability?

Reliability: cause-specific repairs and fresh statement verification avoid treating a
successful command as recovery. Unknown/stale probes fail closed. Measure missed
deadlines, correct results, verified repair time and collateral effects. A shared
control plane, database and healer remain single points of failure in this lab.

Security: scoped Kubernetes access, positive VM identity, pinned SSH, typed
capabilities, approval and a policy witness constrain effects. The historical private
network-policy repair was demonstrated once for the earlier workload and is not promoted for autonomous
reuse. Powerful management credentials remain a risk; no production security or
intrusion-remediation claim is established. Never treat telemetry as instructions.

Performance: synthetic probes and cloud/API calls consume work. Prometheus and
Grafana measure statement latency, queue state, host and Pod resources and loop duration.
Current repair times include guardrails and fresh verification; they are not
all outage duration. No new controlled overhead comparison has been completed
for the focused application.

Scalability: two workers and replicas exercise node separation, not enterprise
scale. The serial controller, single operator, SQLite state and finite credential
lifetime limit this release. No claim of hundreds of managed services, automatic
capacity scaling or high availability follows from seven supporting VMs.

## Reporting boundary

Only the Kubernetes bank statement service is active. Old nginx/DNS/Redis/checkpoint source
and results are archived on the laptop. Detailed current histories also remain
local by user choice; the repository publishes numeric results and limitations.
Preserve failed protocols and distinguish native recovery, configuration repair,
job outage and security correction in every report.


## Banking-specific answers and evaluation (16 October 2026)

1. **Which failures?** Reviewed endpoint drift, absent worker capacity and unsuitable worker memory are recoverable without modifying financial records. Unknown causes, ledger inconsistency, privileged compromise and database disaster are not automatically repairable in this PoC.
2. **Which methods are effective?** Combine independent correct-result/deadline checks with infrastructure evidence, then repair the cause from a reviewed reference. Compare native Kubernetes recovery separately. The lab cannot establish a universally best method; compare success, latency, outage and safety costs per fault.
3. **How does it learn?** Persist distinct verified incidents, human investigation and recipe outcomes; explicitly promote a scoped procedure. Scope change, suspension or failed verification prevents blind reuse. This is case-based procedural reuse, not reinforcement learning or guaranteed fault prevention.
4. **What are the trade-offs?** Measure customer reliability and correctness, authorisation/TLS/integrity refusals, observer/controller overhead and queue latency. Scoped permissions and audit improve control but do not eliminate a privileged attacker. Seven VMs and small synthetic fixtures do not demonstrate enterprise scale.

[DNB](https://www.dnb.nl/voor-de-sector/open-boek-toezicht/wet-regelgeving/dora/) and [AFM](https://www.afm.nl/nl-nl/sector/themas/belangrijke-europese-wet--en-regelgeving/dora/digitale-operationele-weerbaarheid) provide Dutch regulatory context. The [DORA regulation](https://eur-lex.europa.eu/eli/reg/2022/2554/oj), especially recovery, reconciliation and learning provisions, informs the explicit control/gap mapping. These sources do not prescribe MAPE-K or our lab time targets. [PostgreSQL 16 TLS documentation](https://www.postgresql.org/docs/16/libpq-ssl.html) supports verify-full endpoint validation. [ISO 20022 definitions](https://www.iso20022.org/iso-20022-message-definitions) identify a real statement-message domain; our JSON/CSV is explicitly not a conforming implementation.

The live acceptance run verifies 18 properties against real PostgreSQL and the deployed API, including a separate scratch restore. Repeat repair trials use one approved, one recorded-human/promoted and eight automatic occurrences per core fault. Roles are scripted, order is fixed and samples are small: do not infer a causal human-versus-automation speed advantage or general bank reliability. Historical hashing/nginx measurements remain historical.

## Completed banking evidence

[The banking validation report](../evidence/banking-validation.md) records 30 verified core occurrences, 24 automatic reuses, 18 live acceptance checks and a separate browser-approved policy repair with real advisory model responses. Customer failure was observed in all ten worker-capacity occurrences and in none of the endpoint/memory occurrences. The latter demonstrate configuration correction alongside native Kubernetes availability protection, not healer-created zero-downtime recovery. The quiet 12-sample window is too small for a general false-positive-rate claim. No controlled overhead/load-scale comparison or novel-failure prediction was demonstrated. The original four research questions remain applicable, with these explicit limits.
