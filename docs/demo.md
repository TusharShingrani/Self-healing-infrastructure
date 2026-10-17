# Demonstrate the platform healer

## The story to explain

“A bank's gateway platform needs to open many outgoing connections during a retail peak. Even correct application code can fail when Linux resource limits prevent those operations. This experiment reproduces the resource failure inside an isolated infrastructure fixture and verifies a bounded runtime repair without restarting its process.”

This is not a payment application and not a claim of 50,000 requests/second. Network failure here is **outbound local-port allocation**, not inbound connection handling or a cyberattack.

## Screens

1. Console: live resource observations, incident evidence, approvals, verification, procedure qualification and audit trail.
2. Grafana dashboard **Kernel & platform tuning — MAPE-K**, UID `platform-mapek`, using a recent relative time range.
3. Private experiment output, retained on the laptop. Publish only reviewed numeric summaries.

## Automated rehearsal

On the management VM in this checkout run `python3 experiments/native_workflow.py`. This is an explicit laboratory operator script: it deliberately generates bounded fixture pressure and supplies approvals through the same deployed API as the browser. The script's automatic approval steps are **not** the healer approving itself.

It runs two distinct descriptor failures with named operator approvals, explicitly promotes the qualified procedure and runs a third occurrence without a new approval. It then tests outbound-port exhaustion with approval. It checks same identity, useful allocations/connections, the untouched host port range and baseline restoration. It saves detailed JSON privately under `~/.local/state/platform-healer/evidence/`.

## Manual video protocol

Have an administrator start demand only on the owned canary fixture; the web UI intentionally cannot send arbitrary host commands or change resource policy. Stop the rehearsal first to avoid competing operators.

1. Begin at idle: demand zero, descriptor soft limit 64, isolated range size 32. Explain that these are deliberately low lab bounds.
2. On worker-2 set the root-owned `/run/platform-healer/fixtures/descriptors/desired` file to `128`. Show the measured `EMFILE` counter increasing and useful allocations stuck below demand.
3. Show the pending incident: exact target, evidence and proposed bounded action. Before approval no limit should change.
4. Enter a reviewer name and meaningful reason, then approve. Show the soft ceiling becoming 256, held allocations reaching 128 and the incident becoming **verified**, not merely “executed”. The process identity remains unchanged.
5. Set demand back to `0`. Wait for lease expiry and baseline restoration before the next occurrence. The lab lease is 30 seconds; busy rollback is deferred rather than forced.
6. Repeat once. Promote the procedure after the second verified occurrence, with a named reviewer. Run a third matching occurrence: it should repair automatically. Show the audit trail and absence of a third approval. Use **Suspend automatic reuse** to revoke that permission.
7. For networking, use `/run/platform-healer/fixtures/ports/desired` = `96`. Show actual allocation failure, approve range expansion from 32 to 256 available port numbers, then show 96 established connections plus the independent fresh echo verification. Drain and observe rollback. Allow TIME_WAIT to clear before repeating; never change TCP reuse rules to make the demo convenient.

Load is loopback-only and capped; every burst expires after 120 seconds. A failed condition is a finding to investigate, not permission to suppress validation or enlarge safety bounds.

## What to say about learning

“The system remembers a reviewed, verified procedure and its precise applicability scope. It does not invent arbitrary fixes, train an LLM or guarantee prediction. An unknown failure needs investigation and a reviewed adapter/policy addition. Replacement process identity or failed verification prevents blindly reusing an old procedure.”

## Storage finding

The discovered K3s server uses SQLite. The bounded benchmark compares a separate temporary-file durability operation under a best-effort versus idle competitor. It does not stress the control plane. In the initial run, priority change did **not** provide consistent benefit; therefore automatic I/O repair is disabled. This refusal is part of the safety demonstration.
