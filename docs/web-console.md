# Operator web console

The console is an interface to the existing job-service operator workflow.
It does not grant the model new repair capabilities or bypass verification.
Its first supported application is `jobs-lab`; see [the use case](focused-use-case.md).

## Install on the healer

Use the existing Python 3 environment and checkout. No frontend build or npm
dependencies are needed. Run these commands as the same Ubuntu user as the loop:

```sh
cd ~/projects/expanded-infrastructure
python3 tools/console.py --set-password
bash tools/start_console.sh start
```

The password prompt is masked. Only a salted scrypt hash is stored in
`~/.config/healer-console/auth.json`, mode 0600. Do not commit or share that file.
The console service inherits the loop user's existing in-memory credentials.
It does not accept CloudStack or model keys through the browser.

On your laptop, add a forwarding to your existing verified healer SSH command:

```sh
ssh -N -L 8085:127.0.0.1:8085 -L 3000:10.1.1.50:3000 ubuntu@10.53.14.225
```

Include the private-key option from your working SSH setup if necessary.
Open **http://127.0.0.1:8085** exactly; Host and Origin validation intentionally
reject alternative hostnames. Do not expose port 8085 through the cloud firewall.
The HTTP connection is loopback only; the external connection is encrypted by
SSH. This implementation is not intended to be published directly to a network.

## Demonstrate the story

1. Overview: show independent job completion, controller mode and every required
   cause/security check. Stale or absent evidence displays Unknown, never healthy.
2. Incidents: inspect symptoms, evidence, uncertainty and bounded proposed plan.
   Investigate an unknown cause and select an already reviewed recipe. Model
   advice is shown separately; generated text cannot execute a command.
3. Approve or reject the current plan with a rationale. Approval is single-use
   and the engine checks that resource identity and evidence are still current.
4. Alternatively repair through your normal trusted administration path, then
   choose Verify my manual repair with the corresponding reviewed recipe. A
   fresh independent job and cause-specific checks must pass before it counts.
5. Repair memory: inspect cases, scopes and audit entries. After two distinct
   verified occurrences, request promotion. Promotion itself is guarded by the
   existing operator code. A label saying validated is historical state, not
   proof of eligibility in today's scope; current eligible counts are exported
   by the job loop and dashboard.
6. Repeat the same controlled failure and verify actual automatic repair and a
   fresh job outcome. Keep timestamps and raw evidence; do not infer success
   from a green button or cached observation.

Application contract lists the approved configuration and repair boundaries.
Free-form application edits are deliberately not implemented in this first
release: they would invalidate reference identity and learned procedures.
Reference changes remain reviewed repository changes. The refresh preference
only changes display polling. No incident, recipe or arbitrary shell editor is
exposed. A generic service-registration wizard remains future work.

## Tests and limitations

```sh
python3 tools/test_console.py
python3 tools/test_jobs.py
```

Console tests exercise the real HTTP handler, password checking, session expiry
through logout, login throttling, same-origin/Host rules, CSRF, static resource
allowlisting, stale-evidence refusal and typed CLI argument validation. They use
a fake backend and do not prove that a live cloud repair works. Job adapter
tests separately exercise target and recipe guards.

The service is a single-operator prototype. It has no enterprise identity
provider, multi-tenant authorization, TLS listener, distributed lock or HA.
Only one console process is supported. The loop's own freshness/ownership guards
still apply to every executed repair. Long-running manual verification is a
synchronous request; inspect the incident before retrying after a disconnection.
Do not deploy a second controller against the same state and resources.
