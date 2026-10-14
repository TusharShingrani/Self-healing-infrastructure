# Operator workflow validation, 14 October 2026

Implemented a persistent terminal review gate, supported human repair capture,
and candidate/validated/revoked procedures. New live repairs default to review.
Original A/B/C results and the earlier guided demo remain unchanged historical
evidence of the previous execution policy.

## Tests

- 24 operator tests: pending/duplicate/rejected cases, expiry, VM identity and
  changed evidence/reference checks, distinct-occurrence validation, failed
  manual verification, arbitrary-command refusal, scope isolation, revocation,
  root-specific checks, unchanged high-risk gate, unknown-cause refusal,
  advisor evidence and known credential redaction.
- Existing suites: 18 safety, 36 learning/advisor, 66 adapter, 39 host scripts.
- The Windows sandbox prevented temporary-file replacement in the existing
  tests. Those suites were run successfully on the healer's Linux checkout.

## Live proof on app-1

`operator-live-2026-10-14.txt` records the scripted operator exercise.
The first occurrence stayed pending with no automatic repair. Evidence named
nginx and `/etc/nginx/conf.d/healer.conf:15`, where the deliberately injected
`worker_processes` directive was invalid in that context. The approved action
restored the reference config and verified service/config/HTTP health.

On the second occurrence, a separate SSH command copied the reference,
validated `nginx -t` and reloaded/restarted nginx. `record_human` independently
checked it. The two distinct verified occurrences allowed explicit promotion.
After honouring the existing cooldown, the third matching failure was repaired
automatically by the validated procedure. Reopening the database retained its
validated status. The script played the operator role; a person did not type
the decisions during this automated exercise.

An earlier pilot failed when service evidence changed between diagnosis and
approval. The gate correctly refused to reuse the approval; cleanup restored
the configuration. The pilot cases are exported separately. The final protocol
uses a deliberate failed restart after each config injection so occurrences
have comparable service state. No stale approval check was weakened.

## Limits

This validates the workflow on one supported guest repair and target. It does
not establish unrestricted troubleshooting, learning arbitrary shell scripts,
or automatic high-risk platform actions. Unknown diagnoses stay under human
review. A terminal interface is implemented; no web operator console is claimed.
Two successes are an engineering promotion threshold, not statistical proof
that a procedure can never fail. Failed verification revokes automatic use.

The runtime operator database is preserved alongside the original Knowledge.
New procedures are scoped to target/project/template/service/paths/reference
contents and diagnosed symptoms/action plan. Existing safeguards remain.
