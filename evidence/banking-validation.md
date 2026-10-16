# Verified banking release — 16 October 2026

The managed service is fictional monthly account-statement generation. These results were collected from the deployed Kubernetes API/workers, PostgreSQL and independent client. Earlier hashing/nginx experiments are historical.

## Verification results

- **187** retained regression checks pass, including banking money/request invariants, real HTTP boundaries with mocked storage, adapter/approval guards, integrity-action refusal, AI data minimisation and cross-service advice deduplication. These offline tests do not themselves establish cloud behaviour.
- **18/18 live acceptance checks** pass: concurrent idempotent retries, account authorisation, exact statement/hash, rejected untrusted/wrong API TLS identity, restricted DB roles, immutable completed records, one acceptance audit event, separate-database restoration with exact restored document and ledger reconciliation, and bootstrap of an empty disposable database with restricted roles.
- **30/30 core repair occurrences** verify; 24 use promoted automatic procedures. Each fault has one investigator-approved occurrence, one separately applied/recorded and promoted occurrence, and eight automatic occurrences. Roles in these trials are scripted.
- **Three** core procedures remain eligible across controller restart. No database/node/network procedure is promoted for banking automation.
- **14/14** monitoring targets are up; all **21** dashboard queries return data; all **11** required banking checks pass. Integrity and certificate-expiry alerts are installed.
- A quiet window contains **12/12 healthy independent samples** with no new incident. Median completion is approximately **0.102 seconds**. This is a small healthy-window observation, not an overhead, throughput or scalability benchmark.
- The post-core scan reconciled **7,808 completed statements**, found zero missing accepted records and zero audit-count mismatches. A later supporting-workflow scan reconciled more than 9,700 completed statements. Normal new in-flight requests are evaluated separately against the 30-second deadline.
- The real browser generated a reconciled statement and downloaded a CSV with five transactions and a closing balance of **442,206 cents**.

## Core experiment results

| Fault | Verified | Automatic reuse | Median injection to verified | Range | Customer-failure occurrences |
|---|---:|---:|---:|---:|---:|
| Wrong database endpoint | 10/10 | 8 | 17.53 s | 16.49–21.08 s | 0 |
| Zero desired workers | 10/10 | 8 | 91.79 s | 83.43–96.74 s | 10 |
| Unsuitable memory template | 10/10 | 8 | 17.74 s | 16.89–24.84 s | 0 |

Time starts at injection and includes evidence settling, scripted decisions, rollout and fresh verification. It is **not customer downtime or human response time**. Healthy old Pods preserved customer service during endpoint/memory rollout faults; zero workers did breach the client deadline. All measured intervals were below the lab's 180-second recovery target. Fixed order, small samples and scripted roles prevent a causal human-versus-automation comparison.

## Separate human/AI workflow demonstration

One private network-policy drift exercise was kept outside the 30 core trials. The console showed failing policy and independent isolation checks while correct statements continued. Gemini 3.5 Flash-Lite returned advisory hypotheses. The incident remained pending until an investigation bound the reviewed policy recipe and a separate browser approval authorised it once. The engine restored isolation, independently denied the unrelated monitor destination, verified a fresh statement, and marked the incident verified. The policy procedure remains approval-only. A real provider response proves integration, not general diagnostic accuracy.

## Findings that changed the implementation

1. The initial scratch restore held its validation connection open, so cleanup failed. Explicit closure fixed it; the full restore and empty-schema checks then passed. No live database was overwritten.
2. An old pending hashing advice record could suppress a banking request. Advice deduplication now includes bank service/configuration scope; a regression and the real provider exercise verify the new path.
3. A post-experiment scan initially treated one newly accepted pending request as an incorrect completed statement. The checker now uses a read-only repeatable-read snapshot, reconciles completed documents and separately checks overdue pending requests. No financial data was changed to make the check pass.
4. Fresh provisioning still created the retired hashing queue and deletion schedule. New provisioning no longer does so; the existing old schedule is archived and inactive. The banking schema was tested in an empty disposable database, but complete empty-project VM redeployment has not been rehearsed.

Detailed timestamps, request/resource identifiers, incident evidence, AI text, controller history, source hashes and private recovery archives are retained on the laptop by user choice. This repository publishes only source/configuration, numeric/boolean summaries and limitations. Private archives were checked for readability and include a database dump, consistent controller SQLite copies, deployment references and private trust/client material. Scratch DB restoration was tested; full site/key-loss recovery was not.

This is a DORA-informed PoC, not regulatory compliance, formal TLPT, production banking security or high availability. Unknown/integrity failures require investigation; the healer never rewrites ledger entries or acknowledged statements. See [controls and gaps](../docs/dora-control-mapping.md), [research answers](../docs/research-synthesis.md) and [demo walkthrough](../docs/demo-video.md).
