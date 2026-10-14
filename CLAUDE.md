# Project working brief

Read [the current architecture](docs/architecture.md),
[handover](docs/healer-handover.md), [operator workflow](docs/operator-workflow.md)
and [research synthesis](docs/research-synthesis.md) before changing live code.

This research lab has four Ubuntu VMs, not containers. Healer 10.1.1.205 runs
two MAPE-K services. app-1 10.1.1.60 runs nginx and a synthetic transaction;
app-2 10.1.1.61 runs nginx plus dedicated DNS/Redis; monitor 10.1.1.50 runs
Prometheus/blackbox/Grafana. Nginx metrics use 9105, dependency metrics 9106.
Check service WorkingDirectory and Git revision before assuming a checkout is
live. State is relative to each active checkout and is not in Git.

## Safety and evidence requirements

- Never destroy, rebuild, reboot or inject faults into the healer or monitor.
- Preserve runtime Knowledge **and operator databases**, host pins, lab keys,
  infrastructure state, original evidence and private generated credentials.
- Stop both loop services before code/state migration. Stop user services
  directly if preserving their memory-only credential environment; the nginx
  stop wrapper deliberately removes that environment.
- Never reset either app while the dependency lab is operating. The template
  is plain Ubuntu and does not contain the current stack.
- Never disable host-key checks or accept an unexplained changed key. Verify
  through the cloud console. First contact uses trust on first use.
- Keep secrets out of Git, prompts and logs. Credentials come from environment
  variables/user manager. Do not print the full manager environment.
- Faults, scans and security experiments stay inside the isolated lab.
- Do not count a claimed repair, manual cleanup, stale scrape or unknown probe
  as success. Preserve raw samples and the verification contract.
- Unknown dependency patterns need investigation, a bounded recipe and first
  approval. Two verified occurrences plus explicit promotion allow exact scoped
  reuse. Failed automatic repair revokes the procedure. Human notes are evidence,
  never executable commands. New capabilities need review.
- Gemini is advisory; no unrestricted shell execution or automatic investigation
  binding. Do not claim model training or measured LLM diagnostic accuracy.

## Development and verification

Shared orchestration is in mapek/loop.py and stages.py. Nginx adapter is
educloud.py; composite adapter/typed recipes are infrastructure.py and
config/repair-recipes.json. operator.py implements persistent review and
procedure validation; knowledge.py stores history/prevention/advice.

Run all eight offline suites listed in README. They use fake clients/mocked
commands; they must never change production host identity files. Validate shell
syntax and Prometheus configuration/rules, regenerate dashboard JSON from its
source, and update diagrams and recovery instructions when the topology changes.
Record exact live revisions and verification separately from historical results.

The research questions concern healable failure classes, effective methods,
learning/prevention, and reliability/security/performance/scalability. Published
work already includes learning. Do not claim universal effectiveness or fleet
scaling from this small pilot. See docs/repository-audit.md for the current review.
