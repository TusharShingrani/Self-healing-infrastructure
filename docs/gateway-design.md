# Real gateway integration: implementation decision

The primary managed element is the distribution-packaged HAProxy HTTP gateway on
worker-2. An independent client on probe-1 submits nonce-checked HTTP transactions
through that gateway to an owned bounded upstream responder. This responder is a
test instrument, not banking business logic. No additional VM is needed.

The gateway has its own Linux network namespace and veth link. Only the benchmark
VM may reach its private frontend. It has no Internet/default route. The upstream
listens on loopback and a local Unix health socket inside this namespace. Under
bounded concurrent requests the gateway's backend connections exhaust a reduced
32-port ephemeral range. Diagnosis requires sustained correlated namespace
allocation failure, HAProxy connection/HTTP errors and independently healthy
upstream evidence. HAProxy's generic `econ` counter alone is not interpreted as
an errno: a separate namespace allocation probe supplies the errno evidence.

The 32-port range, backend server-close mode and disabled backend reuse are
deliberate lab settings that expose independent outgoing TCP allocation. They
do not imply a default or well-pooled HTTP/2 banking gateway fails at this load.
Production connection pooling and destination diversity require separate tests.

The approved effect expands only this namespace's range to 256 ports. Neither
HAProxy configuration nor its process is restarted. Verification requires stable
successful transactions and the same executable/configuration/process identity.
Headroom, reserved-port conflicts, cooldowns and a fresh upstream-health check
gate execution again at the root broker. Unknown evidence fails closed.

Three operator modes are explicit and audited: observe only, require approval,
and allow already-validated procedures. The last mode does not itself qualify a
procedure. Observations and learning history persist across mode changes.

Evaluation compares the same bounded load under all three modes, records client
success/failure/latency and useful recovery, and includes refusal cases. Existing
socket/descriptor fixtures remain opt-in regression instruments; the default
console and dashboard focus on the gateway. Storage tuning stays unsupported.

HAProxy runtime statistics reference:
https://docs.haproxy.org/2.8/management.html#9.1
Linux namespace port allocation reference:
https://www.kernel.org/doc/html/latest/networking/ip-sysctl.html

Production gateway integration, ingress TLS, corporate IAM and HA require separate
qualification. This work does not establish payment correctness, 50k RPS,
zero packet loss or DORA compliance.
