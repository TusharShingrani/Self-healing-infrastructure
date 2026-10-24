# What breaks, and exactly what the healer changes

This is a reading guide to the implemented mechanism. The example readings below illustrate the rule; they are not a new experiment result.

## The service and its failure

A client on **probe-1** sends an HTTP request to **HAProxy on worker-2**. HAProxy opens an outgoing TCP connection to a synthetic backend and forwards the request. The backend supplies a nonce response so the client can check that a useful transaction completed.

Each outgoing connection needs a local source port. The experiment deliberately restricts the Linux network namespace to **40000–40031: 32 port numbers**. Controlled held connections consume that capacity. This is a laboratory constraint; normal production defaults are much larger. The range is one part of TCP allocation, not a universal one-port/one-request capacity formula.

When that pool is exhausted, HAProxy cannot establish new backend connections even though the backend itself is healthy. Clients see failed HTTP transactions. Restarting does not remove the configured range restriction; the continuing load can consume it again.

![Numbered failure-to-recovery walkthrough](diagrams/incident.svg)

## What each MAPE-K stage does

| Stage | Concrete input or operation | Why it matters |
|---|---|---|
| Monitor | Broker collects `used_ports`, `range_size`, `allocation_probe_errno`, HAProxy connection-error/5xx counters, local HTTP result, upstream health, memory headroom and reserved-port conflicts. It also pulls probe-1's HTTP result. Agent relays this evidence to the controller. | An HTTP failure alone does not identify its cause. |
| Analyse | Example: 32/32 used, errno 99, both error counters increasing, both local and separate-host transactions failing, upstream healthy, safe headroom, no conflict. The implemented rule requires at least 85% occupancy and two consecutive eligible diagnoses. | Correlates the resource error with customer-visible failure and excludes some alternative causes. It does not prove every possible root cause. |
| Plan | Select the existing `expand_port_range` procedure for this exact gateway identity. Include expected old value, approved new range and lease. | No arbitrary shell command or LLM-invented repair. |
| Authorise | In reviewed mode, operator approves the incident with a name and reason. A later tick dispatches. Observe mode never dispatches; automatic mode requires a matching promoted procedure. | Approval is permission for a bounded action, not a direct write from the browser. |
| Execute | Controller sends authenticated intent through the agent. Root broker rechecks identity/value/safety, journals the operation, then changes **only the namespace's `net.ipv4.ip_local_port_range` from `40000 40031` to `40000 40255`**. Configured lease: 30 seconds. | Makes 256 port numbers available without restarting HAProxy or changing the VM-wide setting. |
| Verify | Controller requires correct range readback and three distinct successful probe observations spanning at least two seconds, within a 20-second window. Checks validate HTTP status and nonce body. | Setting a kernel value is not evidence that requests recovered. |
| Knowledge | Store incident, exact scope, action, evidence and verified/failed outcome. After two verified occurrences since the last failure, a named operator may promote the procedure for that scope. Failure suspends reuse. | Learning is guarded procedural reuse, not automatic training or general troubleshooting intelligence. |

## The separate rollback path

The root broker's watchdog continues independently of the controller. After the lease expires it waits for zero active connections and restores the baseline only if the identity and current value still match its recorded operation. Busy connections defer rollback; changed values or identities produce a conflict rather than an unsafe overwrite. **Thirty seconds is a lease expiry, not a guaranteed restoration time.**

## A different failure gets a different outcome

If the backend stops, the upstream check fails. The diagnosis is dependency unavailable, and **no port expansion is allowed**. Missing/stale evidence, unsafe memory headroom and reserved-port overlap also block this repair. The operator investigates; optional Gemini advice can help explain the supplied evidence but cannot execute a repair or add an executable procedure.

That is the current boundary: the project repairs **one qualified outgoing-port exhaustion condition**, detects/refuses several incompatible conditions, and supports investigation of others. It does not automatically heal every HAProxy, VM, network or backend failure.

## Read the architecture by responsibility

- **HAProxy namespace on worker-2:** the thing whose connection capacity is repaired.
- **Controller Pod on worker-1:** requests observations, diagnoses, gates the fixed plan, verifies and records outcomes.
- **Agent Pod on worker-2:** authenticated transport between controller and host broker; not the root repair authority.
- **Root broker on worker-2:** narrow privileged actuator, durable operation journal and independent lease watchdog.
- **Probe VM:** separate client vantage point. Its results reach the controller through the broker/agent, so the reporting path is not independently trusted.
- **Prometheus/Grafana on monitor VM:** metrics and historical display; they do not approve or execute repairs.
- **Console:** operator view of incidents, approvals and procedures; not the service being healed.
- **Gemini:** optional advisory explanation, outside the execution authority.

Use the [network diagram](diagrams/network.svg) for addresses and endpoints, the [MAPE-K diagram](diagrams/mapek.svg) for responsibility boundaries, and the [design specification](design.md) for full contracts and limits.
