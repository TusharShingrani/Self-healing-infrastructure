# Demo video: a bank statement request that survives a worker failure

## Explain the story first

“This fictional bank's customer requests a monthly account statement. The request must finish correctly, remain private and survive a worker configuration failure. Kubernetes runs the application. A separate MAPE-K manager diagnoses and repairs reviewed configuration, obtains approval for new procedures and verifies the actual statement before remembering the outcome.”

Show [the request-path diagram](architecture.md), then the three console tabs. Do not begin with a wall of VM metrics.

## Preparation

Connect the VPN, use the pinned SSH key, open the private console tunnel and Grafana. Run from `~/projects/bank-statements`. Check that no controlled experiment is already running and that all required checks are fresh and healthy. Preserve Knowledge; never delete history to make learning look new. Use only synthetic accounts. Hide passwords, tokens, SSH paths and raw private histories when recording.

## Recording sequence

1. **Normal customer:** Request a September statement. Show the opening balance, transactions, totals and closing balance. Download CSV. Explain that an accepted request is stored in PostgreSQL and retries use the same idempotency key.
2. **What monitoring means:** Open Follow the self-healer. Show customer completion/correctness checks and worker capacity. Open Grafana for the timeline; a running container alone is insufficient.
3. **Controlled worker fault:** In the isolated lab, use the reviewed `tools/job_faults.py` worker-capacity scenario. The exact command is `python3 tools/lab_shell.py python3 tools/job_faults.py workers --controlled-experiment`. Inspect its help first. Label this as injected configuration failure, not a cyberattack. Do not inject while another experiment owns the lab.
4. **Customer impact:** Request a statement. Retain its request identifier. With zero workers it stays pending and breaches the completion objective. Do not resubmit to hide the failure.
5. **MAPE-K:** Show the capacity mismatch and evidence. If already learned, explain that automatic repair is expected. To demonstrate human control instead, suspend that specific procedure in Inspect learned memory **before** injection. For an already investigated cause, inspect its existing bounded plan and approve it once. Only a genuinely unknown cause needs a new investigation binding first. Do not erase history to manufacture a first occurrence. To show a missed deadline, allow the pending request to exceed 30 seconds before approval. The backend remains the authority.
6. **Verification:** Show capacity restored, the original pending statement completed and a fresh independent statement reconciled. Approval alone is not success.
7. **Learning:** Show the distinct verified occurrences and promotion conditions. A suspended or changed-scope procedure cannot silently act. Following deliberate revalidation/promotion, repeat the same fault and show automatic reuse with a new audit outcome. Explain that the LLM was not retrained and arbitrary unknown faults still require investigation.
8. **Banking safety:** Show acceptance-test results for cross-account refusal, immutable records, idempotent retries and backup restoration. Explain the production gaps and DORA-informed design without claiming compliance.

## Honest evidence

Keep detection time, repair time and customer downtime separate. A rolling configuration fault may be repaired before any customer outage. Show unsuccessful checks and the initial restore-cleanup finding rather than cutting them out. Scripted investigator/operator roles in repeat trials are not an independent human usability experiment.

After recording, verify the deployment's reviewed settings, worker count and memory template, fresh correct statements, monitoring freshness and procedure state. Leave no fault, pause file or pending unsafe experiment behind. Never demonstrate ledger corruption as something the healer can safely rewrite.
