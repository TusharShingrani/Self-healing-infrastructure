# HAProxy self-healing system: design specification

**Baseline:** qualified EduCloud gateway profile, reviewed 20 October 2026. This describes the implemented solution and its configuration. Addresses and settings are lab inventory, not a generic enterprise template. No credentials or private histories are included.

## Read this first

The system restores **outgoing connection capacity at one real HAProxy gateway**. A deliberately small pool of 32 source ports in an isolated Linux network namespace can become exhausted under bounded held connections. New backend connections and client transactions then fail. The approved action temporarily expands that namespace's pool to 256 ports. The controller verifies useful requests; the broker later restores baseline safely. It does not restart HAProxy or change the host-wide port range.

Kubernetes hosts the **controller and node agent**. HAProxy, the synthetic backend and root broker are **native VM services**. A separate probe provides an independent network vantage point. Prometheus/Grafana observe the system but do not authorise repairs. Gemini supplies optional advice with no execution authority.

A fictional banking traffic peak motivates the availability problem. The lab has no banking application, payments, customer data or compliance claim. Correct static sizing and connection pooling remain relevant alternatives. The small pool is an experimental constraint, not an estimate of default production HAProxy capacity.

### Reading order and files

| View | Question answered | Preview | Editable source |
|---|---|---|---|
| Existing architecture | What is already deployed? | [Original runtime map](architecture.md#runtime-map), retained | Existing Mermaid block |
| Whole solution | How do the components fit together? | [View 01](diagrams/solution.svg) | [Mermaid](diagrams/solution.mmd) |
| Network | Which machine connects to which endpoint? | [View 02](diagrams/network.svg) | [Mermaid](diagrams/network.mmd) |
| MAPE-K | Who decides, acts, verifies and learns? | [View 03](diagrams/mapek.svg) | [Mermaid](diagrams/mapek.mmd) |
| Incident | What happens during one failure? | [View 04](diagrams/incident.svg) | [Mermaid sequence](diagrams/incident.mmd) |

All four additions are pages in [haproxy-system-design.drawio](diagrams/haproxy-system-design.drawio). Open it in diagrams.net/draw.io and select a page along the bottom. Vector symbols, text labels, boundaries and connectors are separate editable objects. No remote logo/image library is needed. The [gallery](diagrams/README.md) renders the Mermaid sources on GitHub.

Single arrowheads show the **request/action initiator**, not the direction response bytes travel. Replies use the same connection. Blue denotes telemetry requests, orange admitted effects, green workload traffic, purple advice/investigation and grey administration. Labels also explain the meaning without colour. The MAPE-K and incident pages show logical progression rather than network connections or measured durations. Detailed flows deliberately live on separate pages.

## 1. Whole solution

![Whole solution](diagrams/solution.svg)

The operator reaches the console through the management tunnel and private token session. A controller tick requests a sample from the agent. The agent requests it from the native broker over a Unix socket. The broker checks gateway identity, collects local measurements and pulls the latest probe result. This relayed sample becomes the deterministic diagnosis input.

An eligible fixed plan passes the operator-mode gate. The controller persists an exact operation ID and HMAC envelope before dispatch. The agent checks the mTLS caller identity and forwards the intent. Root admission rechecks the target and safety conditions before the broker journals and applies the namespace-only effect. The controller queries operation/sample/verification results through that same path. Verified outcomes enter Knowledge. Broker lease expiry and rollback are separate from controller verification.

**Independence has a limit:** HTTP checks originate on another VM, but results reach the controller through worker-2's broker/agent. This is an independent vantage point, not an independently trusted reporting path or attestation. Prometheus directly scrapes the probe, but that scrape is not a controller decision input.

## 2. Deployment inventory

| Machine | Address | Role | Experiment boundary |
|---|---|---|---|
| healer-ubuntu | 10.1.1.205 | Bastion, administrator checkout, archives and tunnels | Protected |
| monitor | 10.1.1.50 | Prometheus, Grafana and blackbox readiness probing | Protected |
| k8s-control | 10.1.1.80 | Single K3s server using SQLite; management NodePort entry | Protected, no control-plane saturation |
| k8s-worker-1 | 10.1.1.81 | Controller Pod, Knowledge PVC and image builder | Hosts control software, not the patient |
| k8s-worker-2 | 10.1.1.82 | Agent Pod, native broker, HAProxy namespace and upstream | Only owned gateway namespace is a repair target |
| probe-1 | 10.1.1.84 | Independent observer and bounded load | Separate owned traffic source |

Qualification covers Ubuntu 24.04 / Linux 6.8 / K3s 1.36 and the recorded distribution HAProxy 2.8 package. It does not cover every release or distribution. No production ingress controller, Kubernetes application repair, etcd repair, CloudStack runtime adapter or node replacement is enabled.

## 3. Network and connection catalogue

![Network](diagrams/network.svg)

### Management access

1. The laptop connects to EduCloud OpenVPN. Its VPN address may change.
2. Existing forwarding IP `10.53.14.225:22` maps SSH to bastion `.205:22`. Source rules must admit the actual authorised VPN address. This forwarding IP is not the VPN server.
3. Laptop localhost `8085` forwards to bastion localhost `8085`. Bastion user service `platform-console-tunnel` SSHes to `.80`, forwarding to `.80:30885`, the controller NodePort. The service forwards to the controller Pod on worker-1 port `8085`.
4. Laptop localhost `3000` and `9090` forward through the bastion to monitor `.50:3000` and `.50:9090`.
5. Administrator helpers SSH from the bastion to the five configured VMs with a private key, strict pinned host keys and hostname validation. Runtime Pods do not receive that key.

The browser uses HTTP inside the explicit private SSH tunnel. There is no public console web-port exposure or enterprise HTTPS/SSO gateway.

### Runtime and observability connections

| Initiator | Destination | Transport | Purpose |
|---|---|---|---|
| Controller | `platform-agent.platform-healer-system.svc:9119` | HTTPS / private-CA mTLS | Sample, operation state, verification and HMAC effect requests |
| Agent | `/run/platform-healer/broker.sock` | Local Unix socket | Fixed protocol, no shell endpoint |
| Broker | `10.1.1.84:9106/status` | HTTPS / mTLS | Separate-host result and observation time |
| Probe checks / load | `10.203.0.2:18080` | Private HTTP | Nonce transactions and held-request test load |
| HAProxy | Namespace `127.0.0.1:19080` | Loopback HTTP | Synthetic backend |
| Broker | `haproxy.sock`, `frontend.sock`, `upstream.sock` | Local Unix sockets | Counters, local gateway and separate backend transactions |
| Prometheus | `.80:30919/metrics` | HTTPS / monitor mTLS role | Agent NodePort to Pod 9119 |
| Prometheus | `.84:9106/metrics` | HTTPS / mTLS | Direct observer scrape |
| Prometheus | `.80:30885/metrics` | Private HTTP | Controller counts and liveness |
| Prometheus | Six VMs on `9100` | Private HTTP | Node exporters |
| Prometheus | Blackbox local `9115`, target `.80:6443/readyz` | HTTP to exporter; CA-verified HTTPS to API | Readiness, not Kubernetes write permission |
| Prometheus | Local `127.0.0.1:9090` | HTTP | Self-monitoring |
| Kubelet | Agent `9120/healthz` | HTTP | Narrow broker-reachability health endpoint |
| Kubelet | Controller `8085/healthz` | HTTP | Loop liveness |
| Controller, opt-in | `generativelanguage.googleapis.com:443` | Verified HTTPS | Numeric evidence and advisory JSON |

The eleven scrape targets are self, six node exporters, agent, observer, controller and API readiness. Logical service names avoid inventing static Pod/ClusterIP addresses.

### Gateway packet path

Management uses `10.1.1.0/24`. Gateway veth uses host `ph-gw-host=10.203.0.1/30` and namespace peer `ph-gw-peer=10.203.0.2/30` in `platform-healer-gateway`. Probe has route `10.203.0.2/32 via 10.1.1.82`. The namespace returns only to probe `.84/32 via 10.203.0.1`, with **no default route**.

Dedicated forwarding chain `PLATFORM-GATEWAY` permits probe `.84` to `.2` TCP 18080 and established return traffic, then rejects other traffic through that veth. Bootstrap does not flush CNI rules. Backend `127.0.0.1` means the **namespace's loopback**, not host or laptop loopback.

HAProxy exposes TCP and local Unix frontends. Backend `http-server-close` and `http-reuse never` deliberately expose outgoing TCP allocation. Connection pooling, destination diversity and realistic production traffic need separate tests.

## 4. Kubernetes and host boundaries

| Object/service | Implementation |
|---|---|
| Controller Deployment | `platform-controller`, namespace `platform-healer`, one replica on worker-1, Recreate strategy for one SQLite writer |
| Agent DaemonSet | `platform-agent`, namespace `platform-healer-system`, selector restricts it to worker-2 |
| Container security | UID/GID 10001, non-root, RuntimeDefault seccomp, no privilege escalation, read-only root filesystem, all capabilities dropped, no service-account token |
| Container resources | Each requests 25m CPU / 32 MiB and limits 250m CPU / 96 MiB |
| HostPath exception | Agent mounts `/run/platform-healer` read-only, supplemental group 64532 connects to Unix socket. Read-only mount does not make the protocol read-only |
| Pod Security | Agent namespace privileged policy level accommodates hostPath, but the container itself is not privileged. Controller namespace is restricted |
| Knowledge PVC | `knowledge`, 1 GiB, ReadWriteOnce, `/state`, local-path storage dependency |
| Configuration | `controller-settings` ConfigMap, `controller-keys`/`agent-tls` Secrets, optional `gemini-advisor` Secret |
| Broker | Native `platform-healer-broker.service`, root, private Unix listener, restart on failure |
| HAProxy | Native `platform-gateway.service`, user haproxy, no capabilities, namespace-bound, maxconn 128, one thread, MemoryMax 192 MiB, CPUQuota 30%, LimitNOFILE 4096 |
| Backend | `platform-gateway-upstream.service`, user haproxy, same namespace, bounded synthetic responder |
| Observer | `platform-gateway-observer.service`, ubuntu, no capabilities, MemoryMax 64 MiB, CPUQuota 15%, TasksMax 24 |
| Reconstruction | `platform-gateway-route.service` on probe; `platform-gateway-bootstrap.service` on worker-2 |

Default-deny network policies have explicit controller/agent, DNS and management/monitor exceptions. A specific `10.42.0.0/32` lab source exception handles node-origin/SNAT access; it is not a whole assumed Pod CIDR. The advisor helper adds current resolved public IPv4 destinations on 443. CNI/NAT or provider-DNS changes require administrative review. Enterprise hostname-based egress is not implemented.

## 5. MAPE-K decision and verification

![MAPE-K](diagrams/mapek.svg)

### Monitor

The controller sleeps one second after a completed serial tick, rather than guaranteeing a sample each wall-clock second under slow I/O. The agent requests the broker's fixed sample. Its contract contains target, kind, pinned identity, time, metrics and supported/error flags. Generic freshness is ten seconds with two seconds of tolerated future-clock skew. Independent observer evidence is stricter: at most five seconds old, matching the fixed target, with a boolean success value. Clock alignment matters.

The root gateway plugin reads namespace range/reservations/sockets, HAProxy backend `econ` and `hrsp_5xx`, host MemAvailable/MemTotal, a local gateway transaction and a separate backend Unix transaction. At occupancy of 80% or above, a real allocation probe supplies errno; below that threshold it reports zero. Only the separate probe supplies `client_transaction_ok` and `independent_probe_time`.

High historical counters do not establish new failures. Diagnosis and console deltas compare fresh same-identity observations. Missing evidence, resets, unsupported data or identity changes must not become zero/healthy.

### Analyse

The actionable signature requires all of:

- Valid current and previous samples from the same identity.
- Occupancy at least 85% of the namespace pool and allocation errno 99 (`EADDRNOTAVAIL`). HAProxy `econ` alone is not an errno.
- Both connection-error and HTTP-5xx counters increasing.
- Both local gateway and separate-host client transactions failing.
- Healthy backend, safe memory headroom and no reserved-port conflict.
- Two consecutive matching actionable diagnoses before proposal.

Other causes attach no executable port repair: backend unavailable, unsafe headroom, reservation conflict, unknown/missing/stale evidence and unexplained HTTP failure. Data validity, backend, memory and conflict checks precede exhaustion inference. Incomplete signatures require investigation rather than a guessed action.

### Plan and permission

The profile enables target `gateway-ports`, kind `gateway_ports`, action `expand_port_range`. Baseline `[40000,40031]` and expansion `[40000,40255]` are exact reviewed values. Neither the operator nor model supplies an arbitrary executable action parameter.

| UI mode | API | Permission |
|---|---|---|
| Watch only | `observe` | No new effects, even for previously approved proposals |
| Ask before repairing | `reviewed` | Named approval and reason of at least eight characters |
| Reuse reviewed repairs | `automatic` | Matching validated scope/cause/action may reuse permission; root admission remains |

Approval only commits `approved` to Knowledge. A later tick must still see the eligible diagnosis, pass mode checks and observe baseline before dispatch. Healthy idle recovery resolves unused pending/approved incidents, revoking unused permission. Mode changes do not cancel safe reconciliation of an active lease.

### Execute and root admission

The controller creates a canonical HMAC-SHA256 envelope: version, UUID operation ID, target, identity, action, expected current value, fixed parameter, decision reference, issue time and lease. The configured lease is 30 seconds. That exact envelope and `dispatching` state are durable **before** the remote request. HMAC is shared-key authentication, not an asymmetric signature or non-repudiation.

The agent requires mTLS CN `platform-controller` for POST `/execute`; monitor certificates are read-only. It has no HMAC key, so it can forward but cannot mint an authenticated intent. The root broker checks the schema/HMAC, issue age (at most 60 seconds, two seconds future tolerance), UUID and bounded lease (protocol 5–120 seconds, profile 30). Changed content under an old ID is refused. Explicit bounds/admission/cooldown refusals are durable and cannot later execute using the same ID.

Root admission checks policy target, allowed action, fresh sample and same identity, expected current value, parameter shape/exact approved value, no active lease and five-second post-lease cooldown. Gateway admission requires healthy backend, at least **256 MiB and 15%** available host memory, no reserved overlap and at most 128 active backend connections. `apply()` revalidates immediately before entering the pinned namespace and writing the sysctl. The low-level helper also checks namespace ownership/inode, rejects the host namespace, checks reservations and confines its port operation to reviewed infrastructure bounds.

The broker journals `applying` before mutation, checks write readback and records `applied`. Ambiguous timeouts are reconciled by persisted operation ID. A new ID is not generated to blindly retry a possibly successful write.

### Verify and learn

Verification lives **inside the controller**, not in another verifier service. It requires an applied broker lease, same identity, fresh sample, the expanded range, healthy backend/local gateway/independent client and successful broker `/verify`. Three successful distinct probe timestamps must span at least two seconds within the 20-second dispatch deadline. Re-reading one observer record cannot increment the count. An unsuccessful check resets the window; deadline failure records `failed` and suspends reuse.

Execution `deadline` is not lease expiry and must not be shown as a rollback countdown. A successful sysctl write alone is not useful-work recovery. The relevant process/start/executable/configuration/namespace identity must remain unchanged.

Knowledge retains incidents, before/after evidence, actor/reason, outcomes, audit, procedures, investigations, human repairs, executions, persisted modes and verification windows. Scope hashes identity, kind, target and protocol version. Two distinct verified occurrences **after the last failure for that scope/cause/action**, then explicit named promotion, allow reuse. Failure suspends the procedure; replacement/reconfiguration produces a new scope. Manual repair notes and Gemini reports cannot qualify an action. This is reviewed procedural reuse, not model training, automatic runbook invention or predictive prevention.

## 6. Broker lease and rollback

The broker watchdog reconciles every second and reconciles persisted operations before serving after restart. Controller failure does not remove that watchdog; broker failure removes it until restart. Broker journal and controller Knowledge are separate databases.

At expiry, or recovery of an incomplete application, the broker samples again. Changed identity becomes `identity_changed` without a write. If the value already equals baseline, it records `rolled_back`. A value differing from its own applied value becomes `conflict`, preserving an administrator's change. Nonzero active backend connections produce `rollback_deferred`, retried later. Only the same identity/value and drained connections allow baseline restoration and readback.

Recovery and rollback are different events: a verified incident can coexist with an active lease or later deferred rollback. Conflicts, inaccessible broker state and deferred work remain operator-visible conditions.

## 7. One incident end to end

![Incident walkthrough](diagrams/incident.svg)

The [sequence source](diagrams/incident.mmd) expands the calls, state commit before effect and independent broker watchdog. The comparison uses probe-1's 24-second/64-worker bounded workload. The generator accepts only hostname probe-1, 5–30 seconds, 1–80 workers, a fixed destination and bounded recorded events. Systemd also limits time, memory, CPU and tasks. This is owned synthetic test traffic, not an attack or financial workload.

The outage precedes an eligible incident. Correlated evidence, named approval or validated scoped permission, root admission and actual client recovery form the evidence chain. Study recovery must occur while background load continues. Planned held-request cancellation at shutdown is not customer transaction loss. Drain, lease rollback and cooldown precede another run. See [demo](demo.md) and [dated validation](../evidence/validation.md).

## 8. Console and advisory investigation

**Overview** shows four measured values, request path, actual range/errno/TIME_WAIT, safety prerequisites and recent activity. Unknown is not zero. Display deltas reset on stale/missing evidence, identity changes, counter reset or a long gap. **Incidents** has master/detail selection, recorded MAPE-K ledger, deterministic evidence, advisory report, fixed decision and independent verification. Missing event timestamps are labelled. **Knowledge** exposes exact-scope outcomes and promotion/suspension. **Audit log** retains named decisions. **Settings** opens the policy drawer.

Login produces an in-memory one-hour session with HttpOnly, SameSite=Strict cookie and localhost origin checks. Controller restart expires sessions; it does not change the private token. Names are audit labels behind a shared token, not verified enterprise identities. UI JSON requests are bounded to 4 KiB, and mTLS effect bodies to 16 KiB. Health/numeric metrics are separate from authenticated incident access. User/model strings use `textContent`. No AI execute button exists.

Gemini is disabled in a fresh deployment. An administrator adds its Secret and resolved-IP egress. Only numeric/boolean allowlisted evidence and freshness flags leave the lab. Logs, addresses, identity strings, configuration, human notes, full histories and secrets are excluded. Fresh same-identity supported evidence is required. One request runs at a time, at least 60 seconds apart, with a 20-second timeout, 64 KiB reply bound, verified HTTPS, refused redirects and schema validation. Provider failure becomes unavailable rather than another execution route.

Reports and locally computed safety notices are advisory. The model cannot gather more evidence or prove root cause. Operators can investigate and repair through administrator access, then record the change and reported verification. A new automatic action still needs implementation, bounds/refusals, reproducible testing and independent qualification.

## 9. Observability

Prometheus scrapes and evaluates every five seconds. Grafana has four time-series panels and seven queries: independent HTTP-check duration; used ports/range ceiling/active connections; one-minute increases of HTTP 5xx/connection errors; and available-memory ratio. Duration is an individual probe measurement, not p95 or production throughput. Counters are shown as new increases. The range ceiling uses step interpolation.

Nine alert rules cover unavailable telemetry, stale sample, unreachable broker, stalled controller, failed independent transaction, unhealthy backend, rollback review states, pending approval and host memory pressure. These rules do not establish an external notification service; no added Alertmanager/on-call integration is claimed. Prometheus's direct observer scrape corroborates the controller's relayed evidence but does not decide repairs.

## 10. Security and trust

The kernel, VM root, broker/policy/key and controller signing authority are trusted. Broker capabilities include SYS_ADMIN, NET_ADMIN, SYS_PTRACE, CHOWN and DAC_OVERRIDE for namespace entry and different-UID identity inspection. These are substantial privileges. There is a Unix mutation listener, not a public TCP one. The broker's outgoing probe mTLS material is also a credential-bearing part of the trusted base.

Agent/observer APIs use private-CA mTLS with minimum TLS 1.2, verified CA and role certificates. HMAC uses the same private key in controller Secret and root broker. Stolen controller key/certificate exposes root-policy-bounded authority. mTLS does not attest honest telemetry from a compromised node. Foundation node-exporter/controller scrape traffic remains private HTTP. SQLite audit and archives are not tamper-proof. The shared operator token does not provide enterprise identity or independent separation of duties.

Administrators generate an Ed25519 CA and role credentials outside Git. Leaves expire after 90 days; deployment refuses fewer than seven days remaining. Automated renewal/revocation is absent. Enterprise identity, comprehensive telemetry encryption, managed hostname egress, certificate lifecycle, independent reporting/attestation and stronger privileged-base assurance require separate work. See [security](security.md).

## 11. Data and file inventory

| Location | Content and ownership |
|---|---|
| Controller `/state/knowledge.db` | Durable Knowledge, SQLite WAL and FULL synchronous mode |
| ConfigMap `/etc/platform-healer/controller.json` | Targets, bounds, defaults, origins and provider settings |
| Controller `/run/keys` | Mounted node HMAC key, operator token and client mTLS material |
| Agent `/run/tls` | Server certificate/key and CA |
| Worker-2 `/etc/platform-healer/policy.json` | Private root-owned target/admission policy |
| Worker-2 `/etc/platform-healer/node.key` | Private shared HMAC key, not an asymmetric signing key |
| Worker-2 `/etc/platform-healer/tls` | Probe-client CA/certificate/key |
| Worker-2 `/var/lib/platform-healer/journal.db` | Separate broker operation/refusal/lease database |
| Worker-2 `/run/platform-healer/broker.sock` | Root/group 64532 Unix listener, mode 0660 |
| Worker-2 `/run/platform-healer/gateway-identity.json` | Protected root registry outside HAProxy-writable socket directory |
| Worker-2 `/run/platform-healer/gateway/` | HAProxy stats, local frontend and upstream sockets |
| Worker-2 `/etc/platform-gateway/gateway.cfg` | Gateway configuration included in identity checks |
| Probe `/etc/platform-observer-tls` | Observer server mTLS material |
| Bastion `~/.config/platform-healer/pki` | Private administrator CA and role material |
| Bastion `~/.local/state/platform-healer/backups/` | Consistent private recovery directories, copied to laptop |
| Probe `/var/tmp/platform-gateway-results/` | Detailed bounded-load JSON |

Identity incorporates boot ID, namespace inode, PID/start, expected UID/cgroup/executable, executable/config hashes, registry and root policy. Registry reads reject symlinks, unsafe ownership/permissions and non-regular files. FIFO input must not block root sampling.

SQLite retains records without an implemented automatic retention/pruning policy. The observer keeps an in-memory deque of 120 results. Operator sessions and controller observation/streak caches are in memory. There is no claim of infinite storage or durable full observer history.

## 12. Deployment, upgrade and recovery

Administrator scripts verify pinned SSH identities/hostnames, install source/services, generate PKI, render Kubernetes objects, build a digest-pinned Python image on worker-1 and import it into worker runtimes. Secrets travel through SSH stdin rather than Git or command arguments. Runtime Pods lack administrator SSH keys, CloudStack credentials and Kubernetes API tokens. Only gateway-ports is enabled by the root profile; old fixtures are opt-in regression code.

Before an upgrade, stop owned load, confirm zero active connections and baseline, back up state and use the documented deployment/acceptance checks. Explicit bootstrap installs or reconstructs the namespace/identity; it is not a routine repair during active load. Replacement/reconfiguration changes scope and requires requalification.

`backup_state.py` uses SQLite online backup for Knowledge and journal and includes node policy/key/TLS, gateway config, operator token and administrator PKI. Keep it private and copy off-platform. Checksums/readability/integrity prove archive consistency, not a complete disaster reconstruction. Preserve administrator access and pinned host keys too. Never destroy the bastion or sole control plane as an experiment.

Post-boot reconstruction is provisioned, but the recovery comparison does not establish a full VM-reboot/disaster-rebuild drill. Broker restart reconciles before serving. Controller restart resumes persisted operation identity and marks interrupted advice unavailable. Do not transplant an old registry onto a replacement process. See [installation](install.md).

## 13. Availability, evidence and limits

There is one gateway, controller, PVC and K3s server. Broker-watchdog separation does not create high availability. Cloud reclamation, unavailable telemetry, stopped broker and deferred/conflicted rollback remain real possibilities requiring visible uncertainty and review.

Evidence includes the dated mode comparison, paired restart baseline, refusal tests and constructed-case Gemini study. Tests and synthetic browser fixtures are not live fault evidence. Current acceptance covers eleven monitoring targets and populated charts. All 101 tests execute locally/CI with Node; five Node view-model tests skip on the management host. The 20 October walkthrough additionally showed reviewed port recovery and backend-outage refusal. Its private history is illustrative evidence, not another set of comparison repetitions.

Scope is observable, reversible resource-bound saturation with safe admission, reviewed procedural reuse and useful-work verification. No predictive prevention, self-written arbitrary repair, fleet scaling, enterprise HA, attack attribution, payment correctness, DORA certification or general diagnostic accuracy is claimed. [Research](research.md) maps the four questions and further experiments.

## 14. Implementation traceability

| Contract | Source |
|---|---|
| Inventory and administrator access | [config/educloud.json](../config/educloud.json), [deploy_lab.py](../scripts/deploy_lab.py) |
| Pods, services, policies and defaults | [render.py](../manifests/render.py) |
| HTTP/auth/advisory scheduling | [controller.py](../src/platform_healer/controller.py) |
| Tick, mode gate, dispatch and verification | [engine.py](../src/platform_healer/engine.py) |
| Correlated signature/refusal precedence | [analyse.py](../src/platform_healer/analyse.py) |
| Scope, outcome, promotion and manual notes | [knowledge.py](../src/platform_healer/knowledge.py) |
| Agent caller role and endpoints | [agent.py](../src/platform_healer/agent.py) |
| Unix broker/socket/watchdog | [broker.py](../src/platform_healer/broker.py) |
| HMAC schema and validity | [model.py](../src/platform_healer/model.py) |
| Root journal/leases/rollback | [leases.py](../src/platform_healer/leases.py) |
| Gateway identity/admission/observer pull | [gateway.py](../src/platform_healer/plugins/gateway.py), [host_helper.py](../src/platform_healer/host_helper.py) |
| Routes/filter/native services | [bootstrap-gateway.sh](../host/bootstrap-gateway.sh), [bootstrap-observer.sh](../host/bootstrap-observer.sh), [install-broker.sh](../host/install-broker.sh) |
| Independent checks/load | [gateway_observer.py](../src/platform_healer/gateway_observer.py), [gateway_load.py](../src/platform_healer/gateway_load.py) |
| TLS/bounded transport | [tls.py](../src/platform_healer/tls.py), [transport.py](../src/platform_healer/transport.py) |
| AI privacy and opt-in egress | [investigation.py](../src/platform_healer/investigation.py), [configure_investigation.py](../scripts/configure_investigation.py) |
| Metrics/chart queries/rules | [monitoring/build.py](../monitoring/build.py) |
| Private recovery content | [backup_state.py](../scripts/backup_state.py) |
| UI and operator workflow | [operator_ui.py](../src/platform_healer/operator_ui.py), [operator guide](operator-guide.md) |

Claude reviewed public source read-only and discussed page structure, arrow direction, HMAC terminology, approval persistence, relayed probe evidence and verification/rollback separation. Codex checked the relevant production paths and authored these artifacts. This is an assisted consistency review, not an independent security audit or proof of every possible behaviour.

The existing runtime Mermaid in `architecture.md` remains intact. Added Mermaid is editable text, draw.io is uncompressed XML, and SVG exports are self-contained. `python scripts/build_design_diagrams.py` regenerates draw.io/SVG from its layout specification without contacting or changing the lab. Manual draw.io edits do not round-trip into the generator; retain them separately or update the specification before regenerating. Recheck labels/routes against this source table after runtime changes.
