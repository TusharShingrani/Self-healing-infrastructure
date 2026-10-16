# Banking operational-resilience controls and limitations

Research updated 16 October 2026. This is a proof of concept using fictional data. It is **not a DORA compliance assessment**, a regulated bank, a formal threat-led penetration test or an automated regulatory reporting system.

[DNB's DORA overview](https://www.dnb.nl/voor-de-sector/open-boek-toezicht/wet-regelgeving/dora/) identifies ICT risk management, incident reporting, resilience testing and third-party risk as relevant areas. [AFM's testing guidance](https://www.afm.nl/nl-nl/sector/themas/belangrijke-europese-wet--en-regelgeving/dora/digitale-operationele-weerbaarheid) supports proportional testing; ordinary lab fault injection is not formal TLPT. The [DORA regulation](https://eur-lex.europa.eu/eli/reg/2022/2554/oj) supplies the legal requirements. The mapping below is an engineering interpretation, not legal advice or certification.

| Principle / DORA area | Implemented evidence | Remaining gap |
|---|---|---|
| Governance and dependency inventory (Articles 5, 8) | One named statement service, explicit targets, dependency diagram and bounded catalogue | No bank management accountability, formal risk acceptance or independent control function |
| Protection and controlled change (Article 9; RTS 2024/1774 Article 17) | Separate API/worker DB permissions, immutable application records, authenticated TLS, namespace-scoped capabilities, reviewed recipes, approval and audit | Single operator; no SSO/MFA, independent four-eyes enforcement, privileged-host assurance or automated certificate rotation |
| Detection (Article 10) | Independent correct-result/deadline checks plus Kubernetes, DB, network and host evidence; unknown is not healthy | No comprehensive security detection, real customer workload or full false-positive study |
| Response and recovery (Article 11) | Cause-directed configuration repair, bounded scope, fresh reconciliation; integrity failure blocks automation | Single-site single-DB design, no disaster failover or demonstrated enterprise recovery capacity |
| Backup and restoration (Article 12) | PostgreSQL dump restored into a separate scratch DB; acknowledged statement and ledger reconciled | Manual backup frequency; no zero-loss disaster guarantee, offsite encrypted backup service or comprehensive key-loss restore drill |
| Learning (Article 13) | Persistent incident/outcome memory, reviewed promotion after distinct verified occurrences, suspension and scope invalidation | Procedure reuse, not general causal discovery or model training |
| Incident handling (Articles 17–19) | Local incident evidence and operator workflow | No formal severity classification, regulatory notification workflow or reporting deadlines implementation |
| Testing (Articles 24–25) | Controlled fault protocol, role/integrity/TLS/idempotency acceptance checks and repeat trials | No formal TLPT, independent adversarial assessment or production-scale testing |
| Third-party risk (Article 28) | EduCloud dependency and reclamation/backup limitations documented; off-platform evidence retained | No contractual bank-grade SLA, exit assurance, supplier register or multi-provider recovery |

## Business objectives and data safety

The independent client has a 30-second statement completion objective. The lab repair target is 180 seconds after repair initiation. These are locally selected experiment targets, not DORA time limits. Preserving accepted requests during configuration repair is a tested property, not an asserted zero-RPO disaster capability. Backup age determines possible loss after a database disaster.

Integer-cent reconciliation and exact transaction comparison matter more than an HTTP 200 response. The application role cannot rewrite the synthetic ledger or alter a completed statement. This is an immutable statement projection with seeded data, not a complete double-entry banking engine. Administrators remain privileged. No claim is made about encryption at rest or tamper-proof external audit storage.

The JSON/CSV demonstration is not a conforming [ISO 20022 bank-to-customer statement](https://www.iso20022.org/iso-20022-message-definitions) implementation. Real customer access would require identity management, consent/authorisation, privacy controls, retention rules, secure key management and institution-specific validation beyond this lab.

## Operational decisions

A configuration fault can be repaired from a reviewed reference. An unexplained wrong balance must be escalated and evidence preserved. The healer must never regenerate ledger facts, erase requests, roll back acknowledged work or treat an AI suggestion as authority. Human approval applies before new procedures execute; a validated procedure only permits later reuse within the same scope.

Availability without integrity is not successful banking recovery. Successful verification requires both a correct customer outcome and the repaired infrastructure requirement. All raw histories and private backup material remain on the laptop, outside GitHub.
