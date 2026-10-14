# Personally testing the current lab

The current lab uses approval and explicitly validated procedures. Follow
[the dependency demonstration](infrastructure-lab.md) for DNS, cache budget,
permissions and stopped-cache failures, and [the operator workflow](operator-workflow.md)
for nginx. Historical A/B/C runs used different automatic-policy settings; do
not reset a current app or delete runtime databases to replay them casually.

## Connect and inspect without changing anything

Connect EduCloud VPN. From your laptop, use the private key matching your healer
login and `ssh ubuntu@10.53.14.225`. Verify an unexpected host key through the
console before changing a pin. If SSH times out, check the approved gateway
firewall source against your current VPN address.

On the healer:

```bash
systemctl --user show healer-loop healer-infrastructure -p WorkingDirectory
# Enter the active checkout, then:
python3 tools/lab_shell.py
bash tools/start_loop.sh status
bash tools/start_infrastructure.sh status
python3 tools/lab.py status
python3 tools/infrastructure.py status
python3 tools/infrastructure.py list
python3 tools/infrastructure.py procedures
curl -fsS http://10.1.1.60/healthz
curl -fsS http://10.1.1.61/healthz
curl -fsS http://10.1.1.60:8088/healthz
```

The nginx responses are `ok`; the transaction returns JSON naming DNS, cache
write and checkpoint checks. Check growing tick counts and fresh timestamps,
not just healthy services. Metrics represent the last completed tick.

For Grafana, keep a laptop tunnel open:

```bash
ssh -N -L 3000:10.1.1.50:3000 ubuntu@10.53.14.225
```

Open `http://localhost:3000/d/selfheal-infrastructure` or
`http://localhost:3000/d/selfheal-mapek`. Dashboards are read-only. Approval and
investigation use the authenticated SSH CLI, not the dashboard.

## Demonstrate learning honestly

Use one fault at a time on app-1/app-2 and allow cooldowns between occurrences.
A procedure already marked validated demonstrates **reuse**, not new learning.
An unknown incident demonstrates investigation, bounded recipe selection,
single-use approval, independent verification, a second verified occurrence and
explicit promotion. A third matching occurrence demonstrates automatic reuse.
Record the incident/procedure ids and actual checks at each step.

Recording a human repair does not run it and does not certify a claim: the tool
performs fresh checks. A failed automatic verification revokes the procedure.
Changed VM identities, references, recipes or symptoms require review again.
This is persistent procedural learning, not model training.

Gemini advice is optional and pending. A real response proves provider
integration, not diagnostic accuracy or permission to execute. Infrastructure
advice cannot replace the investigation/recipe/approval sequence.

## Credentials and recovery

Credentials disappear after reboot. Use the masked entry instructions in
[the handover](healer-handover.md). Do not paste secrets into chat or Git.
Simulation demos are explicitly offline. The controlled live infrastructure
demo requires a new state/evidence path and the infrastructure service stopped,
as explained in its guide. Preserve production state first.

The nginx disk fault uses a bounded 512 MiB filesystem and a deliberately added
startup preflight; the failure occurs at a restart, not because stock nginx
automatically stops on a full disk. Historical measured runs are under evidence/.
Keep raw samples and results off EduCloud and report unsuccessful trials too.
