# Security and recovery boundaries

## Delivered controls

- Non-root controller/agent containers, read-only filesystems, no capabilities, no Kubernetes API token or CloudStack keys. The agent's broker-directory hostPath remains an explicit security exception.
- Private-CA mTLS for agent and independent observer, minimum TLS 1.2, bounded responses and no redirects. The monitor client is read-only; mutation requires controller certificate identity and a separate HMAC intent. Missing TLS material never enables plaintext fallback.
- Root-owned fixed gateway policy, private signing key, expected-value and immutable-identity checks, fresh admission, operation ID replay protection, journal-before-write, root cooldown and bounded leases. Bounds/admission/cooldown refusals are journalled; they cannot later execute under the same operation ID.
- Only the dedicated gateway namespace port range can change. Host range, reserved-port set, HAProxy process, application configuration, Kubernetes workloads and cloud resources are not runtime repair targets.
- Upstream failure, low absolute/relative available memory, reserved-port overlap, stale/missing independent observations, changed identity or excessive connections refuse tuning. No arbitrary AI-generated commands.
- Operator mode changes, approvals, promotion and suspension are durable named decisions. Observe mode blocks effects even for a previously approved incident. Failed verification suspends reuse.

## Privileged computing base

The native broker remains root and uses CAP_SYS_ADMIN, CAP_NET_ADMIN, CAP_SYS_PTRACE, CAP_CHOWN and CAP_DAC_OVERRIDE. SYS_ADMIN enters the positively identified namespace; SYS_PTRACE permits inspecting the different-UID HAProxy process identity through /proc. No ptrace execution endpoint is exposed. SYS_RESOURCE and SYS_NICE are removed from the gateway profile. These are substantial privileges, not an enterprise-safe universal installation. The kernel, node root, broker source/policy/key and controller signing authority remain trusted.

HAProxy itself runs as haproxy with no capabilities in a dedicated namespace. The namespace has no default route; the probe has one explicit route; its veth forwarding chain allows only the owned probe path. The upstream is a bounded loopback service. Load is confined to that gateway, at most 80 requested background connections and 30 seconds per run, with service time/memory/task/CPU bounds. Protected bastion, monitor and sole control-plane are never fault targets.

The pinned identity registry is in the root-owned broker directory, outside the HAProxy-writable socket directory. Registry reads use a non-following, nonblocking descriptor and require a protected root-owned regular file; a FIFO cannot block the privileged collector.

## Remaining limits

Optional Gemini investigation is advisory only and disabled by default. Its numeric telemetry allowlist excludes histories and secrets. It has no broker access, tools or approval authority. Model advice and operator-reported repairs cannot qualify automation. See [AI investigation](ai-investigation.md) for provider configuration, egress, privacy and evaluation limits.

The localhost UI relies on SSH tunnelling plus a private shared operator token, not enterprise SSO or independent separation of duties. The named reviewer is an audit label, not independently verified corporate identity. Foundation node-exporter/Prometheus paths remain private HTTP. mTLS does not attest that a compromised agent reports honest telemetry. Root registry, local SQLite audit and backups are not tamper-proof. No HA, fleet-scale benchmark, OKD SCC/SELinux qualification, automated certificate revocation/rotation, SBOM assurance or production IAM is claimed.

Private Ed25519 CA is generated outside Git; leaves expire after 90 days. Deployment refuses credentials with under seven days remaining. Administrators must plan renewal and replacement; private CA and role keys are backed up off-platform. A stolen controller signing key/certificate still exposes root-policy-bounded authority. Recovery requires secure administrator access.

Legacy descriptor fixtures retain a PID-check/prlimit race and are restricted to isolated regression hosts. They are not enabled in the gateway profile. I/O, host-wide production tuning, reboots, node replacement, arbitrary repairs and public scanning remain unsupported.

## Recovery

Stop only the owned load, let active backend connections drain, and inspect range baseline, lease journal and independent client health. Lease expiry is compare-and-set: administrator changes cause visible conflict. The controller may stop while the broker watchdog continues; a broker outage temporarily removes that watchdog. Reconcile the durable journal after restart before another trial.

Run `python3 scripts/backup_state.py` from the management checkout, then copy its private directory off-platform. It uses SQLite's online backup API and includes Knowledge, node journal/policy/signing key, gateway configuration, operator token and management PKI. Archives do not replace verified administrator SSH access or a tested reconstruction procedure. EduCloud availability and backups are not guaranteed. Never publish keys, tokens, kubeconfigs, raw histories or private archives.
