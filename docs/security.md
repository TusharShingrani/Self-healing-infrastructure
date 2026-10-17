# Privilege and trust boundaries

## Implemented

- Controller: non-root, read-only image, no Linux capabilities, no service-account token, one replica/Recreate, SQLite WAL on a PVC. Operator decisions require a private token/session, checked browser origin, named reviewer and a meaningful reason.
- Agent: non-root DaemonSet, no hostPID/hostNetwork, no service-account token, no capabilities; only a read-only mount of the dedicated broker directory and supplemental GID 64532. Read-only mounting does not make a Unix socket read-only: the fixed broker protocol is the authority boundary.
- Host broker: administrator-installed systemd service; private root-owned policy and key; fixed target/action allowlist; HMAC intent, freshness, operation ID, expected identity, value bounds, compare-and-set and journal-before-write. Expiring leases have a separate watchdog; restart recovery reconciles the journal. Administrative changes are preserved rather than overwritten.
- Network experiment: loopback-only namespace, no external route, at most 128 held connections, fixed destination, 120-second load-burst deadline (one-shot process lifetime capped at 900 seconds). No public scan or attack target.
- Descriptor experiment: separate owned process, hard limit 512, at most 128 held test descriptors, 120-second load-burst deadline (one-shot process lifetime capped at 900 seconds). The root system or real K3s process is never the descriptor target.
- Namespace inode, process start time, root-owned registry and policy digest scope action/learning. Missing or changed evidence fails closed. Deferred rollback is a visible state, not success.

## Explicit lab exceptions and unresolved risks

The broker needs root and `CAP_SYS_ADMIN` for entering the dedicated network namespace, plus bounded resource/network privileges. This is a substantial trusted computing base. It is a **lab exception**, not an acceptable universal enterprise deployment policy. Separate per-plugin brokers, SELinux policy and platform-specific capability reduction need further work.

The agent's hostPath requires a Pod Security exemption; its namespace is labelled accordingly. The controller namespace remains restricted. OKD SCC/SELinux and managed-node support are untested. NetworkPolicies must be checked with the installed CNI; host/node-origin traffic has special semantics. The EduCloud overlay permits signed HTTP within the private cluster and an SSH-tunnelled HTTP UI. Signatures protect mutation integrity but do not encrypt telemetry. Production mTLS and per-node signing-key rotation are not delivered by this release.

PID/start-time checks reduce accidental process replacement, but Linux `prlimit(pid,...)` remains a PID-based syscall: there is a narrow identity-check/syscall race. This release restricts it to owned bounded fixtures. It must not be advertised as eliminating PID reuse races for arbitrary production processes.

The controller and broker keys, root registry, node kernel and container runtime are trusted. A compromised agent could lie about telemetry even though it cannot mint a signed mutation. Responses are not cryptographically attested. A stolen controller key permits the two root-policy-bounded actions; it does not grant arbitrary commands. The local SQLite audit trail is not tamper-proof or an enterprise identity/approval service.

The single controller, local PVC and native broker are availability dependencies. No HA, formal proof of stability, production overload/load-shedding policy or fleet-scale benchmark is claimed. Scope changes invalidate learned reuse and require fresh review.

## Recovery

Drain fixture demand to zero, inspect broker lease metrics and wait for baseline restoration. A busy descriptor process defers lowering its soft limit. Administrative value changes cause conflict and require review. Stopping the controller does not stop the broker watchdog. Stopping the broker itself temporarily removes that protection; restart it and inspect its journal before further tests.

Keep source, administrator SSH access and validated private state backups off-platform: EduCloud availability and backup retention are not guaranteed. Never commit signing keys, operator tokens, kubeconfigs, private SSH keys, incident histories or recovery archives.
