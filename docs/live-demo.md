# Personally testing the self-healing lab

Run the commands below on the healer, from `~/projects/selfheal`, unless a
step says laptop. Faults target only app-1 or app-2. Never inject a fault on
the healer or monitor. A dashboard picture alone is not proof: check the
independent run measurements, loop events and stored rule together.

## Open the dashboard and a terminal

Connect OpenVPN first. If SSH times out, compare the assigned VPN address
with the gateway Firewall rules. Allow only the current address as a `/32`
for TCP 22. Changed host fingerprints need console verification first.

On the laptop, keep this WSL terminal open:

```bash
ssh -N -L 3000:10.1.1.50:3000 ubuntu@10.53.14.225
```

Open http://localhost:3000/d/selfheal-mapek in your browser. Grafana has
anonymous read-only viewing. Choose Last 15 minutes and a short refresh
interval. Open a second terminal with `ssh ubuntu@10.53.14.225`.

```bash
cd ~/projects/selfheal
python3 tools/lab_shell.py
bash tools/start_loop.sh status
python3 tools/knowledge.py events 10
python3 tools/knowledge.py rules
curl -fsS http://10.1.1.60/healthz
curl -fsS http://10.1.1.61/healthz
```

Both responses should be `ok`. The loop should be active. Increasing loop
ticks prove the loop is running; a healthy app alone does not.
`lab_shell.py` opens a shell with the credentials already held in memory by
the running loop's user service manager. It does not print or save them.
After a reboot, it reports missing names; use the masked prompts below.

## Credentials after a reboot

Credentials deliberately disappear after reboot. Enter them into your shell
without putting their values into history, files or chat:

```bash
export CS_URL=https://educloud.fontysict.nl/client/api
read -rs -p 'CloudStack API key: ' CS_KEY; echo
read -rs -p 'CloudStack secret: ' CS_SECRET; echo
export CS_KEY CS_SECRET
export LAB_SSH_KEY="$HOME/.ssh/healer-lab-key"
# Optional, for actual Gemini calls:
read -rs -p 'Gemini API key: ' GEMINI_API_KEY; echo
export GEMINI_API_KEY
python3 tools/lab.py status
bash tools/start_loop.sh start C
```

These credentials go to the user service manager in memory. Do not print
its complete environment. The keypair name `healer-lab-key2` is the cloud
resource; `~/.ssh/healer-lab-key` is the actual private key path.

## What to watch at each MAPE-K stage

| Stage | Observation | Evidence |
|---|---|---|
| Monitor | Availability, nginx unit state, bounded log use/growth and config match | Grafana panels; Prometheus series; `healer_loop_monitor_source_info` identifies Prometheus and direct fallbacks |
| Analyse | Named symptoms become a cause | Diagnosis panel and event `cause`/`source` |
| Plan | Catalogue actions selected, with guest repair before reboot/rebuild | Event `actions`, escalation level, pending approval count |
| Execute | Repair followed by fresh direct probes | `HEALED` event plus independent `/healthz` samples |
| Knowledge | New incident and active prevention rule | `knowledge.py incidents` and `knowledge.py rules` |

The loop ticks every 10 seconds. Host facts refresh every 15 seconds,
Prometheus scrapes every 10 seconds, and growth uses a time window. Panels
therefore have real delay. Post-repair verification uses direct probes,
not the old dashboard scrape. Failed or unknown probes are not healthy.

## A short live repair demonstration

Leave config C running and execute:

```bash
python3 -u tools/live_run.py app-1 service_stop
python3 -u tools/live_run.py app-1 config_drift
python3 tools/knowledge.py events 12
```

The runner injects and measures; the loop repairs separately. Expect the
availability panel to change, a diagnosis and action, then recovery.
`summary.json` must identify config C, confirmed injection, a healed event,
and a healthy final service. If manual cleanup fixed it instead, do not
count that as healing. Commands print their evidence folders.

## Show learning, not just another restart

Learning is a stored rule, not model training or a new shell command. Config
C recalls earlier symptoms and prevention actions. Config B has reactive
repair without that Knowledge; A observes without healing.

If a disk rule already exists, the next run tests prevention, not the first
learning occurrence. For a fresh learning demonstration, stop the loop,
back up runtime state, start with a new Knowledge database, reset and
provision app-1, and restart C. Preserve the old database; do not discard
research results. The 2026-10-14 guided demo saved the previous state under
`~/healer-demo-backups/20261014T092750Z`.

With empty Knowledge and a healthy, provisioned app:

```bash
python3 -u tools/live_run.py app-1 disk_leak
python3 tools/knowledge.py incidents
python3 tools/knowledge.py rules
```

The lab fault removes rotation and fills the dedicated 512 MiB volume.
At +150 seconds the experiment deliberately restarts nginx. Its lab storage
preflight refuses a start with under 25 MiB free. This is an explicit lab
requirement, not stock nginx behaviour. A full log disk alone does not stop
a running nginx process.

After repair, expect a rule triggered by `disk_growing_fast`, with actions
`clear_logs` and `fix_log_rotation`. Let the previous action rate-limit
window expire before a presentation's next independent demonstration
(20 ticks, normally about 200 seconds; allow a little extra):

```bash
sleep 210
python3 -u tools/live_run.py app-1 disk_leak
```

Proof of prevention requires all of these: confirmed fault, a `PREVENTED`
event from Knowledge before the maintenance restart, successful restart,
independent zero-downtime samples, and healthy final probes. If the guardrails
block a prevention action and an outage occurs, record that outcome honestly.
Shared Knowledge can also protect app-2; its rule is not limited to app-1.

## Human approval and LLM advice

There are distinct controls:

- Learned prevention rules are auto-approved in the current service config.
- LLM suggestions are pending until a person approves them.
- Reboot/rebuild require a separate high-risk gate even after advice approval.
- `state/paused` temporarily makes the loop observe without acting.

See pending real advice, then decide by its actual numeric id:

```bash
python3 tools/knowledge.py advice pending
python3 tools/knowledge.py approve-advice ID
# Or:
python3 tools/knowledge.py reject-advice ID
```

Do not approve something simply to make a demo pass. Inspect the cause,
catalogue actions, risk and requested checks. No supported action is a valid
LLM answer. The LLM is asked when diagnosis/repair is stuck, not for every
ordinary fault and not while its known repair rules suffice.

For a repeatable approval demonstration that cannot touch a VM:

```bash
python3 tools/demo_advice.py
python3 tools/demo_advice.py --risky --decision approve
python3 tools/demo_advice.py --real
```

The first two use a clearly labelled fake provider and a simulated target.
The first prompts you to approve or reject and shows the repair counter.
The risky case shows an approved suggestion still waiting at the separate
high-risk gate. The third makes a real Gemini call if `GEMINI_API_KEY` is
exported, but its target remains simulated. It proves provider integration
and human review, not a Gemini-directed live VM repair. The simulator's
stuck metrics agent may have no matching catalogue action; that is expected.

Gemini receives the advisor's symptom/observation prompt, not API credentials
or private SSH keys. Its proposed actions must belong to the fixed catalogue.
Human-approved advice still goes through rate limits, cooldown and verification.

Do not create `state/approve-high-risk` for this demo. Demonstrate that gate
with the simulated target instead of deliberately forcing a real rebuild.

## Evidence and repeatability

Each live run writes `samples.csv`, `summary.json`, `run.log` and
`loop_events.jsonl` under `evidence/runs/`. Samples request `/healthz` once a
second independently of the healer. One run is a demonstration, not a complete
experiment. Keep guided-demo evidence separate from the existing A/B/C results.
Copy raw evidence off EduCloud. Review files for secrets before publishing.

`python3 tools/demo.py` is a simulation, despite its old "live demo" wording.
`tools/live_run.py` is the measured cloud run. Keep that distinction in your
report and presentation.
