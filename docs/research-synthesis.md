# Research synthesis: self-healing infrastructure

Research date: 14 October 2026. This is a structured literature review and an
engineering evaluation plan, not a systematic review claiming exhaustive coverage.
Live results are recorded separately in `evidence/infrastructure-results.json`.

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

A useful boundary is whether the system has observable evidence, a permitted
effector, a known desired state and a trustworthy outcome check. A failure being
detectable does not mean its cause can be repaired automatically. Restoring
availability, correcting a cause and preventing recurrence are different outcomes.

| Failure class | Evidence needed | Possible response | Our lab and limits |
| --- | --- | --- | --- |
| Stopped dependency | Process state plus failed client operation | Start the specific dependency; verify a transaction | Redis on app-2; restarting app-1 cannot repair it. The reason a process stopped still needs investigation. |
| Configuration drift | Difference from approved reference and functional error | Restore approved configuration and validate syntax | Existing nginx plus a dedicated DNS record. Restoration corrects drift, not necessarily whoever caused it. |
| Resource limit misconfiguration | Effective limit, consumption and rejected operation | Restore the approved budget or reduce load | Redis refuses writes under a deliberately wrong maxmemory limit. No host memory flooding is required. |
| Permissions drift | Exact object, owner/mode and denied operation | Restore least-privilege owner/mode | A single lab checkpoint file; never chmod broad trees or loosen permissions indiscriminately. |
| Bounded storage exhaustion | Mount identity, usage trend, rotation policy | Reclaim expendable logs and restore rotation | Existing nginx experiment. Its startup preflight is a declared lab requirement. |
| Partial network/DNS failure | Independent observer, DNS answer, connection result | Restore a known record/rule or route to a healthy dependency | DNS record fault exercised; arbitrary routing and firewall repair remain out of scope. |
| VM failure | Cloud state, guest reachability, storage identity | Reboot or replace stateless VM with explicit approval | Existing platform catalogue. Rebuild is not a data-preserving repair. |
| Overload and retry amplification | Queue, latency, utilisation, dependency topology | Admission control, load shedding or additional capacity | Literature-supported future scenario. No claim that our request-load sweep implements autoscaling. |
| Certificate expiry | Verified expiry, trusted issuer and renewal path | Renew, validate chain, deploy and test | Future scenario; never bypass TLS verification. |
| Data corruption, compromise or physical failure | Integrity evidence, trusted backup or replacement authority | Isolate, fail over, restore verified backup; involve an operator | Not automatically repaired in this lab. Availability restoration is insufficient proof of integrity or security. |

This taxonomy combines established mechanisms with project design choices.
Microreboot demonstrates narrowly scoped recovery; gray failure motivates client
checks; Redis documents the resource error exercised here. None establishes that
every member of a failure class is safely repairable. [Microreboot](https://www.usenix.org/legacy/events/osdi04/tech/full_papers/candea/candea_html/index.html),
[gray failure](https://www.usenix.org/conference/srecon24americas/presentation/li),
[Redis](https://redis.io/docs/latest/develop/reference/eviction/).

## 2. Which methods are most effective for detection and repair?

There is no defensible universal winner. Effectiveness depends on the failure,
the information available, the cost of a false positive and whether state can be
lost. The practical choice for this small lab is a hybrid: deterministic checks
and dependency evidence for detection, investigated recipes for cause correction,
and verified case memory for reuse. This is our inference from the evidence.

| Method | Strength | Weakness | Lab comparison |
| --- | --- | --- | --- |
| Process/liveness check | Cheap detection of fail-stop faults | Running does not imply usable | Record systemd state alongside transaction outcome. |
| End-to-end transaction | Detects actual loss of service | Does not by itself localise the cause; costs work | Resolve DNS, SET/GET an expiring Redis key, write/read one checkpoint. |
| Component checks and dependency graph | Separates failing dependency from affected frontend | Model can become stale; multiple faults complicate attribution | DNS failure blocks cache measurement rather than falsely blaming cache. |
| Threshold or invariant | Explainable, efficient and reproducible | Threshold choice and transient noise matter | Approved memory budget and explicit record/mode contract. |
| Restart-only response | Fast for transient component faults | Does not correct external configuration or permissions | Restart transaction frontend once, then test whether the same failure remains. |
| Cause-directed recipe | Repairs a known invariant with small scope | Requires diagnosis and maintained desired state | Restore DNS, cache budget or checkpoint permissions. |
| Verified case reuse | Reduces repeat investigation for matching conditions | Incorrect generalisation or stale context can cause harm | Exact target, VM identities, template, reference and recipe digests. |
| LLM-assisted investigation | Can help interpret heterogeneous evidence | May misdiagnose; output and telemetry are untrusted | Existing advisor remains advisory. No claim of LLM diagnosis accuracy from the scripted operator demonstration. |

Kubernetes makes readiness and liveness distinct; our transaction follows that
principle without adding a container cluster. Gandalf illustrates contextual
correlation. AIOpsLab demonstrates why diagnosis and mitigation need separate
evaluation. These are reasons for the architecture, not numbers transferable to
our lab. [Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/),
[Gandalf](https://www.usenix.org/conference/nsdi20/presentation/li),
[AIOpsLab](https://arxiv.org/html/2501.06706v1).

Measure detection time, localisation correctness, repair success, verification
success, recovery time, false alarms during healthy requests, operator decisions,
and collateral effects. A proposed repair or a successful command exit does not
count as recovery. A request probe that cannot run is unknown, not healthy.

## 3. How can learning prevent future failures?

There are several distinct forms of learning: remembering successful cases,
updating diagnosis rules, predicting deterioration, and adapting action selection.
Narya is an important counterexample to the old repository claim that existing
systems do not learn. Its production system used experiments and adaptive action
selection. We cannot claim this project's memory is the first learning system.
[Narya](https://www.usenix.org/system/files/osdi20-levy.pdf).

Recent work is even closer to this question. Verify, Augment, Improve uses
verified failed adaptations to improve a predictive model; its ground truth
and training procedure differ substantially from our operational case memory.
This reinforces the need to describe the contribution as a scoped engineering
prototype and evaluation. [Verify, Augment, Improve](https://publikationen.bibliothek.kit.edu/1000196013).

Our implementation uses reviewed case memory because the available data is too
small to justify a trained predictor or unconstrained reinforcement learning.
The unknown incident records component evidence. An investigator names a cause
and binds it to a reviewed recipe. The first execution still needs approval.
An independently performed human repair can be recorded, but its result must
pass direct checks. Two distinct verified occurrences create the evidence needed
for explicit promotion. A matching later occurrence can execute automatically.
Failed verification revokes automatic status.

Recipes are versioned JSON compositions of bounded operations. They cannot
contain shell commands or arbitrary paths. New combinations can be registered
without changing the MAPE-K stages. A genuinely new operation still requires a
reviewed implementation. This gives extensibility without pretending that any
human command transcript is safe automation.

The selector is deliberately narrow. Changes to either dependent VM, deployed
reference files or the recipe book require new investigation and validation.
Human notes are not executed. Unknown conditions and ambiguous diagnoses remain
pending. A healthy period can clear an observation but does not prove a repair.

Faster repair of a recurrence is reactive learning, not prevention. Prevention
requires acting on an earlier signal before a user-visible failure occurs. The
earlier nginx growth experiment provides one bounded prevention example. The
new DNS, memory-limit and permissions experiments primarily demonstrate learned
recovery. Future prevention experiments should separately record warning time,
action time and the absence of failure during an equivalent challenge. They
must also count unnecessary actions and negative outcomes.

## 4. Effects on reliability, security, performance and scalability

Reliability can improve when verified repairs shorten outages, but incorrect
automation can create outages. Availability during a controlled test window is
not a production availability promise. Report failed requests, outage duration,
successful verified repairs and any failures caused by the healer. Metastable
failures show why removing a trigger may be insufficient if amplification
continues. [Metastable failures](https://www.usenix.org/system/files/osdi22-huang-lexiang.pdf).

Security has two sides. Narrow ownership checks, pinned host keys, reviewed
recipes, least-privilege file modes and explicit approval reduce accidental
damage. The healer still possesses powerful SSH and cloud permissions, creating
an attractive target. The cache is disposable, non-persistent and private.
It requires authentication and restricts the transaction client to GET, SET and
PING on lab keys. Command-specific SSH/sudo credentials are not yet implemented.
The lab therefore demonstrates behavioural
safeguards, not a production security boundary. Never treat telemetry as trusted
instructions or repair suspected compromise by merely restoring availability.
[Redis security](https://redis.io/docs/latest/operate/oss_and_stack/management/security/),
[automation experience](https://sre.google/sre-book/automation-at-google/).

The 2026 AIOpsDoom study shows a concrete reason: manipulated telemetry can
steer a remediation agent toward an insecure change. Our recipe schema and
approval boundary reject executable text, but we did not reproduce that attack
suite or implement its complete sanitisation defence. [AIOpsDoom and AIOpsShield](https://www.usenix.org/conference/usenixsecurity26/presentation/pasquini).

Performance must include overhead as well as recovery. Each monitoring cycle
opens SSH connections, calls the cloud API and runs synthetic requests. Measure
cycle time, process CPU and memory, API/SSH call counts and transaction p50/p95/p99
latency. Cap service memory, CPU and task counts. Limits can themselves affect
latency and must be reported. The load experiment compares monitoring absent
and active during twenty-second windows, with alternating ordering where feasible.
[Monitoring](https://sre.google/sre-book/monitoring-distributed-systems/),
[cgroups](https://docs.kernel.org/admin-guide/cgroup-v2.html).

Scalability has at least three meanings: request capacity of managed services,
number of managed nodes, and concurrent incidents. A sweep of 1, 4 and 8 request
workers on two VMs measures only the first. It does not establish that this
serial SSH/cloud loop can manage hundreds of hosts. The two-host transaction is
observed as one composite managed element; component-localisation evidence
preserves the individual targets. Cycle time must remain below the polling
interval. A larger deployment would need cached inventories, controlled
parallelism, sharded loops, distributed state and conflict coordination.
Capacity decisions should use actual resource demand, not QPS alone.
[Overload](https://sre.google/sre-book/handling-overload/).

## Lab protocol and reporting boundary

The original four VMs are retained. nginx and its existing results remain a
separate experiment. app-1 runs a non-root synthetic transaction on 8088; app-2
runs dedicated DNS on 1053 and a bounded disposable Redis on 6380. The healer
runs a separate reviewed loop and operator database. The monitor observes both.
No public scan or host-wide resource flood is needed.

Four new fault classes are exercised: DNS drift, wrong cache budget, checkpoint
permissions and a stopped cache dependency. For each, confirm a healthy baseline,
confirm the injection, record client failure and component evidence, compare a
frontend restart with cause repair, then demonstrate reviewed learning through
two verified occurrences and a promoted automatic recurrence. Scripted operator
decisions are labelled as scripted. A controlled scripted diagnosis is not proof
that the LLM or a person diagnosed an unfamiliar incident independently.

Keep the complete results, cases, audit decisions, resource observations and
timestamps off-platform. The initial small run is a mechanism validation, not
the planned ten-repetition comparative study. That later study should randomise
method order, reset both the services and the intended learning state, retain
failed runs, predefine observation windows and report distributions rather than
one best result. CHESS motivates this steady-state/fault/outcome structure.
[CHESS](https://arxiv.org/html/2303.07283v1).
