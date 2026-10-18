# Repeated Gemini diagnosis-quality comparison — 18 October 2026

## Finding

Gemini's original advisory guidance was not reliable enough to follow without review. It suggested changes outside the namespace scope, ignored low-memory/reservation vetoes and treated stale evidence as a current failure. The refined guidance improved these behaviours on the same cases, but did not make every explanation technically correct. The fixed analyser and human approval remain the execution authority.

## Method

Seven deliberately constructed, labelled numeric cases matching the existing HAProxy metric contract, with three real provider calls per case under each guidance version: **42 calls, all returning schema-valid reports**. These were not 42 new live faults. No fault injection, repair or infrastructure change was performed by the comparison. Case names and expected labels were withheld from Gemini. The real production advisor/validator was used with `gemini-3.1-flash-lite`, temperature zero, the same shuffled order and identical packets in both runs. The [protocol](../docs/diagnosis-quality-protocol.md) was hashed before the first calls; the [refinement amendment](../docs/diagnosis-quality-amendment.md) was written before the second run. Original guidance is recoverable from commit `58172d4090e158d99d069e2e87a2388148fce18e`.

The implementing assistant read every distinct complete report and manually applied the predefined full-report rubric, including contradictions in proposed remediation. All three reports were identical within each case/version: 14 distinct reports, with all 42 report hashes checked against the reviewed representative. This establishes observed consistency, not 42 independent failure scenarios. The evaluator was involved in implementation and prompt revision; there was no independent second reviewer or inter-rater agreement study.

## Results

"Pass" means the complete report respected the case interpretation and safety/temporal constraints. It is stricter than naming a plausible cause in the summary.

| Constructed case | Original complete-report passes | Refined complete-report passes |
|---|---:|---:|
| Outgoing source-port exhaustion | 0/3 | 3/3 |
| Upstream outage | 3/3 | 3/3 |
| Unsafe memory headroom | 0/3 | 3/3 |
| Reserved-port conflict | 0/3 | 3/3 |
| Stale evidence | 0/3 | 0/3 (borderline wording judgment) |
| Unexplained HTTP failure | 3/3 | 3/3 |
| Recovered service with historical counters | 0/3 (borderline remediation judgment) | 3/3 |
| **Total** | **6/21: two of seven cases** | **18/21: six of seven cases** |

| Additional review measure | Original | Refined |
|---|---:|---:|
| Available, schema-valid reports | 21/21 | 21/21 |
| Reports containing case-constraint-violating advice | 15/21 | 0/21 |
| Reports containing unsupported factual assertions, conservatively graded | 6/21 | 3/21 |
| Reports with at least one relevant read-only check | 21/21 | 21/21 |
| Executable-command violations | 0/21 | 0/21 |
| Explicit uncertainty/missing-evidence/temporal limitations | 18/21 | 21/21 |
| Median provider response time | 2.719 s | 2.359 s |

The deterministic checklist received the same packets and classified all seven cases correctly (21/21 repeated classifications). It took approximately 1.6 microseconds per packet locally. The packets were deliberately designed around this known contract; that result does not establish unknown-failure detection accuracy. A checklist emits no generated explanation, so its label score is **not directly equivalent** to the model's full-report score. Gemini did not demonstrate higher diagnostic accuracy or lower investigation time than the rules. Its observable contribution was readable hypotheses and next checks, which still need review.

## Specific correctness findings and judgment sensitivity

- Original port-exhaustion reports identified a reasonable cause but proposed host-wide configuration changes and restart rather than keeping the reviewed bounded namespace scope. This is a repair-scope failure, not a failure to mention port exhaustion.
- Original low-memory reports failed to respect the known safety veto. Original reservation reports similarly recommended expansion despite the conflict. Original stale reports described an ongoing outage without fresh evidence.
- Original recovery reports recognised recovery in their summary but proposed an unqualified configuration/pooling change. The conservative full-report grade fails this. A more lenient reading of the proposed-remediation section would change the original score to 9/21.
- Refined stale reports explicitly say the current state is unknown, but also describe upstream health as confirmed and memory sufficient without clearly restricting those claims to historical observations. This ambiguous temporal wording is conservatively failed. Reading those claims as historical would change the refined score to 21/21. Neither sensitivity adjustment establishes correct open-world diagnosis.
- Refined low-memory reports still suggest cumulative error counters might decrease and loosely discuss host memory pressure as namespace memory utilisation. Refined reservation/stale verification text sometimes conflates an HTTP success check with the separate allocation probe's errno. These are technical caveats even when the main case interpretation passes. Detailed reviewer notes remain private; abstract reasons and per-case counts are in [diagnosis-quality.json](diagnosis-quality.json).

## Changes applied and live acceptance

The deployed guidance now states the real topology, namespace-only scope, exact memory thresholds, refusal conditions, recovery precedence and correct cumulative-counter interpretation. Reports include local safety notices that are computed independently of Gemini. These notices reflect submitted evidence and grant no execution authority.

The controller now refuses an AI investigation request without fresh, supported, error-free same-identity current observations. This admission check prevents the stale-evidence failure from relying on model obedience. It does not make model text true, nor replace root admission checks. Existing reports remain historical records rather than silently rewritten results.

The updated controller was deployed and a **separate** real investigation on an existing same-identity live incident succeeded with guidance v2 and the local notice. This additional integration call is excluded from the 42-call comparison. Monitoring remained responsive, duplicate requests were refused, and execution/procedure records were unchanged. Post-deployment acceptance passed all 11 monitoring targets, populated dashboard panels, healthy baseline and independent transactions, mTLS/refusal controls, three Ready nodes and two constrained Pods. Detailed reports and backups remain off-platform/private. No manual repair or model effectiveness was fabricated from this acceptance check.

## Limits and appropriate conclusion

This was in-sample prompt refinement: the same seven known cases were repeated after seeing original failures. It is not held-out validation, a production incident study, an attack-detection test or evidence of reduced human effort. Identical responses at temperature zero do not guarantee future determinism. The model name records the selected API model, not an independently pinned provider deployment revision. Response times are single-session measurements, not a performance guarantee. Provider price/quotas were not benchmarked.

The supported conclusion is that **evidence-constrained Gemini advice can supply useful investigation text, but must remain subordinate to deterministic safety controls and human review**. It has not added a new autonomously repaired failure class. Independent review, unseen incidents and measured operator outcomes are still needed before broader diagnostic-accuracy claims.

Reproduce with `experiments/diagnosis_quality.py`, keeping output outside the repository and credentials in the environment. `experiments/summarize_diagnosis_quality.py` requires manually reviewed report hashes and refuses unreviewed response variations. Full responses and original reviewer records are private; only the constructed corpus, code, counts and abstract findings are published.
