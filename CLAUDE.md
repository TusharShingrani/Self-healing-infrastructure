# Project context

Read this before doing anything. It is the standing brief for this repository.

## What this is

A final-year HBO ICT graduation project at Fontys, Eindhoven. Roughly 60 hours
of work. The subject is **self-healing infrastructure**: infrastructure that
detects a failure, repairs the cause rather than the symptom, and learns so the
same failure is prevented next time.

The theory spine is the **MAPE-K loop** (Monitor, Analyse, Plan, Execute,
Knowledge). The code mirrors it on purpose, so the report and the modules line
up.

The gap this project addresses: published self-healing systems (Red Hat's
stack, Netflix's Winston, the practitioner write-ups) all stop at detect and
repair. None of them learn. Stages 5 and 6, remember and prevent, are the
contribution.

## Research questions

Main: how can a self-healing infrastructure recover from failures and learn to
prevent them?

1. Which infrastructure failures can be self-healed? (Library + Lab)
2. Which self-healing methods are most effective for detecting and repairing
   failures? (Library + Lab)
3. How can a self-healing system learn from past failures to prevent them?
   (Library + Lab)
4. How does self-healing affect reliability, security and performance?
   (Library + Lab)

Scope is the **infrastructure layer**: services, storage, configuration,
instances. Application code is out of scope. nginx is the managed service
because it is infrastructure, not an application anyone wrote here.

## Where things run

- **healer-ubuntu** (10.1.1.205) is the only instance with a port forward from
  the gateway at 10.53.14.225. The loop and this repository live here.
- **app-1, app-2** are the lab instances, reached over the internal network
  10.1.1.0/24. They do not have port forwards.
- The platform is EduCloud, which is Apache CloudStack. Project
  `healer-lab`. All identifiers are in `config/lab.json`.
- Credentials come from `CS_URL`, `CS_KEY`, `CS_SECRET` and `LAB_SSH_KEY` in
  the environment. `CS_KEY` and `CS_SECRET` are the secrets: **never** write
  them into a file, a commit, a log or a report. `CS_URL` is not a secret and
  is exported from `~/.bashrc` on the healer (outside the repository).
  `LAB_SSH_KEY` is a path; the key file itself never enters the repository.

## State of play

Working and tested, with no live evidence:

- the MAPE-K loop, in three configurations (A no healing, B rules, C rules plus
  knowledge), passing against the simulation
- the EduCloud adapter, tested against a fake API client
- the lab host scripts, tested with mocked system commands
- three suites: `tools/test_safety.py`, `tools/test_adapter.py`,
  `tools/test_lab_host.sh`

Not yet done, and this is the whole point of working here:

- `app-1` has never been deployed from the template
- `tools/install_lab_host.sh` has never run
- no live API call has been made by the adapter
- no real outage has ever been observed
- the loop has never healed anything real

## The immediate objective

Produce **live evidence**, in this order. Do not move on until each step has
real output.

1. `python3 tools/lab.py status` works against the live API.
2. `python3 tools/lab.py deploy app-1` succeeds and the instance is reachable.
3. `tools/install_lab_host.sh` runs on app-1 and all its checks pass,
   including the fill proof.
4. By hand: inject the disk fault, wait, do a deliberate restart, and confirm
   `/healthz` stops answering. Then reclaim space and confirm recovery.
5. Only then let the loop act on it.

Expect things to break. Fix them in this repository, with a test where the
failure was testable.

## How the failure is made deterministic

Stock nginx does not go down when its log volume fills, and it rolls back a
reload it cannot apply. So the lab host declares an explicit startup storage
requirement: an `ExecStartPre` preflight that refuses to start nginx with less
than 25 MiB free on the bounded log volume, and the maintenance operation is a
deliberate restart rather than a reload.

This is a lab protocol modelling a real requirement. Never describe it as stock
nginx behaviour, in code comments or in the report.

## Hard safety rules

- **Never** destroy, rebuild or reboot `healer-ubuntu`. It is this machine.
- Destructive actions only target names in `lab_instances`, and ownership must
  be positively proven. Fail closed on missing metadata.
- Never write to the root filesystem as a fault. The disk fault targets a
  bounded loop-backed volume, validated by `tools/lab-host/healer-mount-guard`
  before anything is written.
- `reboot_instance` and `rebuild_instance` are high risk: the loop records a
  proposal and escalates unless approval is explicitly enabled.
- Fault injection and any scanning stay inside the project's own isolated
  network. EduCloud's terms forbid scanning anything else.
- EduCloud guarantees neither availability nor backups, and projects are
  removed after about six months. Keep code and results off-platform.

## Working rules

- A failed probe is unknown, never healthy. Health requires every required
  probe readable and satisfied.
- Verify after every repair. An action reporting success while the service is
  still down is the failure mode that makes automation dangerous.
- When something cannot be established, say so. Do not report simulation
  behaviour as observed behaviour. The distinction between "the tests pass" and
  "this was observed on the lab" matters more here than anywhere else.
- Capture evidence as you go: command output, timestamps, free space, service
  status, journal lines, curl results. Write them to `evidence/` and commit.
  That directory is the raw material for the report.
- Prefer a test over a promise. If a bug was reproducible, add the test.

## Writing style, for anything that ends up in the report

Plain English, British spelling, no em dashes or en dashes, student voice, no
marketing language. Short sentences. Say what is true, including what did not
work.
