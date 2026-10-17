# Platform validation — 17 October 2026

## Qualified environment

Ubuntu 24.04, Linux 6.8.0-106-generic, K3s v1.36.5+k3s1, cgroup v2. Three Kubernetes nodes: one server and two workers. The server uses SQLite, not etcd. One isolated canary worker, a management bastion, monitoring VM and independent benchmark VM are retained.

## Offline safety and controller tests

36 passing standard-library unittest checks. Coverage includes signature/tamper refusal, target identity and expected-value refusal, bounds, stale requests, duplicate operation IDs, conflicting leases, restart reconciliation, rollback expiry/defer/conflict, missing/unknown probes, correlated diagnosis, approval, verification deadlines, ambiguous transport outcome, explicit promotion and failed-verification suspension. Mocked tests are not live recovery evidence.

## Live mechanism and native workflow

The root broker/engine mechanism protocol passed separately. The native Kubernetes controller then passed the following through its actual operator HTTP API; the rehearsal script deliberately acted as the named laboratory operator for approvals.

| Resource incident | Decision | Incident-open to verified recovery | Useful operations after repair |
|---|---|---:|---:|
| Descriptor occurrence 1 | Operator approved | 3.410 s | 128 held descriptor allocations |
| Descriptor occurrence 2 | Operator approved | 3.502 s | 128 held descriptor allocations |
| Descriptor occurrence 3 | Promoted procedure reused automatically | 2.214 s | 128 held descriptor allocations |
| Outbound port exhaustion | Operator approved | 4.499 s | 96 established connections, fresh echo verified |

Each occurrence included actual allocation failures before repair. The resource/process identities did not change. The networking change was confined to the dedicated loopback namespace; the host ephemeral range stayed unchanged. The descriptor hard ceiling stayed 512. All eight leases across the separate mechanism and native protocols were subsequently observed `rolled_back`, with demand zero, descriptor soft ceiling 64 and isolated range size 32. Controller Knowledge survived the final source rollout, preserving four verified native incidents and one explicitly validated procedure; no pending/executing/failed native incident remained.

The final runtime passed a second native rehearsal after the UI corrections. Its recovery intervals were 3.402 s, 3.425 s, 2.305 s (promoted automatic descriptor reuse) and 4.393 s (outbound ports). Existing automatic permission was explicitly suspended by the rehearsal operator before the two new reviewed occurrences; history was retained. The resulting state contains **eight verified native incidents, one validated procedure, no pending/executing/failed incident and twelve rolled-back broker leases** across the mechanism test and both native rehearsals. The final acceptance check again passed with both canaries idle at baseline.

These are acceptance tests, not a statistically powered comparison. The recorded durations include the scripted operator decision and polling protocol; they do not estimate real human response time. Do not claim a 37% performance improvement, prediction, 50,000 RPS, zero drops or production availability from these four observations.

## I/O capability finding

Three paired temporary-file durability comparisons on the dedicated benchmark VM with its active `mq-deadline` scheduler. Idle-to-best-effort competitor p95 latency ratios: **0.988, 1.012, 0.975**. No consistent material benefit was established. Automatic I/O priority repair remains unsupported. No production/control-plane datastore file was stressed or tuned; no repaired-etcd claim is made.

## Deployment and monitoring acceptance

- Native DaemonSet and controller rollout ready; non-root containers, no service-account token or RBAC grants, read-only root filesystem and dropped capabilities.
- Root fixed-operation broker reachable, both target samples fresh, loop completing ticks.
- Final acceptance checked ten populated dashboard queries, unsigned-action refusal, unauthenticated incident-access refusal, three Ready Kubernetes nodes and two non-root runtime Pods.
- Ten Prometheus scrape targets up: six retained node exporters, agent, controller, Kubernetes-readiness exporter and Prometheus itself. Prometheus validated eight rules.
- Platform-only Grafana dashboard deployed and private localhost console endpoint reachable through SSH tunnels.
- Browser inspection verified the platform sign-in page and dashboard panels. An attempted token-file browser sign-in did not execute because automatic approval review hit a service usage limit. The authenticated API workflow and UI JavaScript checks passed, but a signed-in browser visual check remains unverified.
- Old banking namespace, controller/console and observer retired. Obsolete database and two former nginx VMs destroyed with exact ownership/address/template checks; protected platform nodes retained.
- Fresh old-workload recovery data and new journal/Knowledge/private-key recovery files copied to the laptop. Archive readability and SQLite integrity checked. A full infrastructure disaster restore has not been proven by these checks.

Detailed histories, identities, signatures, I/O measurements, deletion inventory and private backup manifests are retained on the laptop, not in this repository. This public record intentionally contains only a reviewed numeric and acceptance summary.

## Remaining qualification

Only two owned fixture adapters are qualified here. No arbitrary production target, generic gateway/ingress adapter, enterprise IAM/mTLS, distributed controller/HA, attested telemetry, fleet scalability, complete Linux/PID-race elimination, OKD support or DORA compliance is claimed. See the architecture and security documents before extending privileges or targets.
