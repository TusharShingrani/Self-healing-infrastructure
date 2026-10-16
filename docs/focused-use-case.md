# One use case: recover monthly account-statement generation

A fictional Dutch retail bank provides a customer with a September 2026 statement. The customer submits a request, receives a durable request identifier, and retrieves a statement containing opening balance, transactions, credits, debits and closing balance. A failed worker must not require the customer to submit another financial request or change their ledger.

The lab contains two fixed synthetic accounts. It is a statement-generation projection, not a core banking ledger, payment processor or fraud-detection product. JSON and CSV outputs are demonstration formats; they are not ISO 20022 camt.053 implementations.

## Requirements and business impact

| Requirement | Implementation / measurement |
|---|---|
| Correct result | Independent literal fixture checks exact transactions, integer-cent totals and document hash |
| Timely service | Each independent synthetic request has a 30-second completion objective |
| Recoverable operation | Lab recovery target is 180 seconds after repair initiation; report measured times and failures |
| Preserve accepted requests | Requests are durable in PostgreSQL; worker repair must allow queued work to finish |
| Confidentiality | Credential-derived account identity; cross-account reads refused; verified TLS |
| Controlled change | Fixed capabilities, ownership/scope checks, operator approval, fresh verification and audit |
| Repeated failure learning | Two verified occurrences plus explicit promotion; suspend or invalidate on changed scope/failure |

The 30- and 180-second targets are chosen experiment objectives. DORA does not prescribe them. An unavailable statement service inconveniences customers and increases support demand; it does not imply funds have moved or disappeared. An incorrect statement is an integrity incident: stop automation and investigate, never alter ledger values to make a check green.

## Three related infrastructure faults

1. **Wrong database endpoint:** a deployment configuration change prevents new workers from connecting. Restore the reviewed endpoint; a restart with the wrong value repeats the problem.
2. **Worker capacity set to zero:** requests remain accepted but cannot complete. Restore reviewed worker capacity, then verify queued and fresh requests.
3. **Unsuitable worker memory specification:** the desired deployment violates its reviewed resource contract. Restore the reviewed template and verify the rollout and customer result.

Kubernetes may preserve old healthy Pods during a bad rollout. Configuration repair is still useful, but cannot be counted as recovered customer downtime if no outage occurred. Native Pod restart is a platform baseline, not evidence that our controller learned a repair.

Network-policy drift, database availability and compute availability are supporting dependency checks. They are not automatically promoted in the banking catalogue. Unknown causes and financial-integrity failures remain operator incidents.

## Misuse and failure cases

A wrong account credential must not reveal another statement. Duplicate retries must not duplicate work. An operator must not approve stale evidence or promote an arbitrary command. A compromised AI response must not gain an execution capability. A faulty health probe must not turn unknown into healthy. A changed deployment/reference must not reuse old approval silently. A database administrator can bypass application-role safeguards: privileged access and host compromise are outside the demonstrated threat boundary.

## Evaluation boundary

Use controlled faults only in this isolated lab. Preserve raw timestamps, unsuccessful attempts and receipts privately. Report repair success, customer deadline failures, correctness, detection/repair time, repeated-occurrence modes, controller overhead and monitoring coverage separately. Ten occurrences per fault are repeatability checks, not a population-scale reliability estimate or an independently staffed human study.
