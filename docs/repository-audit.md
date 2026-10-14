# Repository audit, 14 October 2026

Base revision: `124da87` on GitHub main, including the concurrently merged
documentation review. The audit began at `1697e9f` and reread the latest snapshot. The audit read all **250 tracked
files**, including source, configuration, documents, raw samples, JSON/JSONL,
historical SQLite databases and the performance figure. The file inventory
records each original path, size, SHA-256 and format checks. Reading/validating
every file is not a formal proof that every possible runtime path is correct.

## Corrections

- Shared host-identity writers now reread under a process lock and publish a
  unique atomic temporary file. A stale writer cannot erase another loop's
  address. Invalid stored identity fails closed instead of resetting history.
- Unreadable independent cache-budget probes enter investigation; malformed
  transaction JSON becomes evidence rather than an uncaught attribute error.
  An unhealthy observation with no named symptom still raises `probe_failed`.
- Fresh approval evidence must have the exact diagnosed symptom set. An extra
  symptom cannot inherit an approved or promoted repair plan.
- Both exporters serve snapshots of completed ticks without waiting for slow
  repair SSH/API calls. Timestamps expose stale snapshots. Alerts cover missing
  exporters, stale loops, failed transactions and unmeasured dependency checks.
- CloudStack error envelopes returned with HTTP 200 are failures, not empty
  successful list/destroy responses. Error messages redact keys and signed URLs.
- Log reclamation enforces its bounded mount guard even when called directly.
  Rotation/log cleanup command chains preserve failures rather than masking
  them with a successful final command.
- The infrastructure advisor uses the dependency context and current registered
  recipe names. It remains advisory; prompts redact known environment secrets.
- A failed installer transfer cannot run stale remote files. The historical
  A/B/C runner's final restart call is corrected and its destructive historical
  policy is explicit; it refuses a running dependency loop or production
  operator database.
- README, architecture diagrams, design notes, working brief, demo and recovery
  instructions describe both adapters and current approval policy. Historical
  results/review are labelled. Original numerical/raw measurement evidence is
  retained. The recovery guide now includes both operator databases, dependency
  state and consistent backup requirements.

## Verification

`bash tools/test_all.sh` runs eight independent suites and syntax checks. The
audit adds regression cases for stale registry writers, corrupt/missing identity,
HTTP-200 API errors, invalid probe payloads, stale approval symptoms, unsupported
unhealthy observations, bounded log effects, redaction, advisor context and an
actual HTTP scrape during a deliberately slow dependency tick.

All original JSON/JSONL records, CSV rows and SQLite integrity checks were read
and validated. Python syntax, shell syntax, local Markdown links, dashboard
generation and Prometheus rules/configuration are checked separately. The
performance PNG was visually inspected; its 37,497-request caption describes
the retained pilot, not a new experiment performed by this audit.

See `repository-file-audit.json` for original file coverage and
`../evidence/repository-audit-validation.json` for the final verification record.

## Live status and deployment boundary

At the pre-upgrade check both loop services were active, all required nginx and
dependency probes passed, all ten Prometheus targets were up, and there were no
recent errors or pending repair incidents. Four dependency procedures were
validated. The healer had about 5 GiB available memory, no swap use and 44% root
disk use. This is a point-in-time health check, not an availability guarantee.

The pre-upgrade nginx checkout was `~/projects/selfheal` at `20f85b8`; dependency
checkout was `~/projects/broader-infrastructure` at `b3189a0`. GitHub main was
newer than either live checkout. These audit fixes are prepared in the isolated review checkout and have not
restarted or upgraded the running services. Current paths/revisions are
recorded in the validation record; do not assume a GitHub merge changes
running services.

The additional `http_unavailable` symptom in current shared code changes some
historical nginx procedure selectors. Their approvals must not be silently
widened. Preserve the historical cases and validate the new selector separately
before claiming automatic nginx reuse under it. Dependency references/recipes
remain the same, but inspect their scope after deployment.

## Remaining limits

Initial SSH contact uses trust on first use. Internal transaction/DNS/Redis
traffic is not encrypted. Operator audit names are self-reported inside an
authenticated SSH account. Knowledge and audit records are ordinary SQLite
databases, not tamper-proof storage. Cooldowns/action budgets are process-local
and restart with a service; they are not a durable fleet-wide rate limiter.

Historical controlled experiments and initial validation scripts are not
production schedulers. Some capture scripts replace their explicitly named
output files; preserve original evidence and choose a fresh destination or
checkout before another experiment. The cold provisioning sequence is documented
but was not replayed by destroying a healthy app during this audit. A template
rebuild alone does not recreate the expanded application stack.

This lab establishes a finite set of verified repair procedures. Unknown and
simultaneous new faults still require investigation. Two verified occurrences
qualify a reviewed procedure; they do not establish general diagnostic accuracy,
production reliability, prevention for every fault, or fleet scalability.
