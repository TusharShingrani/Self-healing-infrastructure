# Design notes: the MAPE-K skeleton and the EduCloud adapter

The original project README, kept for its design reasoning. The current
overview is the top-level README.md.

A working starting point for the project. Pure Python, standard library only,
no dependencies, runs anywhere.

This is a skeleton to learn from and extend, not a finished project. Read it,
change it, break it. You need to be able to explain every line of it.

## Run it

```bash
python3 tools/demo.py            # the story in one screen
python3 tools/experiment.py      # configurations A, B and C, results to CSV
python3 tools/test_safety.py     # the guardrail evidence
```

## What is here

```
mapek/
  world.py        the managed element: a simulated host, and a real Linux one
  stages.py       Monitor, Analyse, Plan, Execute
  knowledge.py    the K: incident store, recall, learned prevention rules
  guardrails.py   cool-down, rate limit, the rules that stop automation looping
  actions.py      the action catalogue: everything the loop is allowed to do
  loop.py         the MAPE-K loop itself, in configurations A, B and C
tools/
  demo.py         same fault twice: it breaks, then it does not
  experiment.py   the experiment, with a CSV for the report
  test_safety.py  six tests that prove the guardrails work
```

## How the code maps to the theory

| MAPE-K | File | What it does |
|---|---|---|
| Monitor | `stages.py` | Turns probe readings into named symptoms |
| Analyse | `stages.py` | Turns symptoms into a cause, not another symptom |
| Plan | `stages.py` | Turns a cause into actions from the catalogue |
| Execute | `stages.py` | Runs them and verifies the result afterwards |
| Knowledge | `knowledge.py` | Records incidents, recalls them, learns prevention rules |

The managed element sits behind `world.py`. The loop never touches the system
directly, only through probes (read) and effectors (write). That is why the
same loop runs against a simulation and against a real host without changes.

## The three configurations

| Config | What it has | Answers |
|---|---|---|
| A | No healing. Watches and records only | The baseline |
| B | Detect, diagnose, repair, verify | What is self-healing worth? |
| C | B plus knowledge: recall and prevention | Does learning help? |

## What the experiment shows

With ten runs per fault per configuration:

- A never recovers, so downtime runs to the end of the observation window
- B recovers from all three faults within one tick
- C does the same, and on a repeat of the disk fault the downtime is zero,
  because the loop acted on the early signs before the failure happened

That last line is the whole point of the project. Everything published on
self-healing stops at B.

## Fault, error, failure

The disk case is deliberately a three-step chain, because it is the example
that separates symptom from cause:

```
fault    log rotation is broken
error    the disk fills up
failure  the service stops
```

Restarting the service treats the failure. Clearing the disk treats the error.
Only fixing log rotation treats the fault. Config C learns to act at the error
stage, which is why the failure stops happening.

## Moving to real servers

`world.py` already has `LocalWorld`, which talks to systemd, the real disk and
a real config file. To move across:

1. Build your lab VMs from code so they can be rebuilt identically
2. Point `LocalWorld` at a real service, log directory and config file
3. Fill in `fix_log_rotation` and `restore_config` with the real repair
4. Run the same experiment against the real host

Nothing in `loop.py`, `stages.py` or `knowledge.py` changes. That is the test
of whether the separation is right.

## What to extend

- More faults, chosen by the criteria from sub-question 1
- A second analyser that asks a sandboxed language model instead of the rules,
  returning a cause and a choice from the same catalogue. Keep the executor
  and the guardrails identical, so the comparison is fair
- Real metrics collection instead of direct probes
- An approval step, so a learned rule only becomes active once a human signs
  it off. `Knowledge(auto_approve=False)` already does this

## Running against EduCloud

Once the lab exists, the same loop runs against real instances. The loop talks
to the managed element only through the interface in `world.py`, so swapping
simulation for the platform is an adapter change. The interface itself has
grown during development (sampling, escalation), and both adapters moved with
it: interchangeability is a property of the interface, not a claim that those
files were never touched.

```
mapek/cloudstack.py   signed CloudStack API client, project scoped, waits on
                      asynchronous jobs
mapek/educloud.py     the real managed element: probes and effectors over SSH,
                      plus reboot and rebuild through the API
config/lab.json       the lab's identifiers. Credentials are NOT in here
tools/lab.py          deploy, check, reset and destroy lab instances
tools/cloudstack_check.py  what the API account is permitted to do
tools/install_lab_host.sh  prepares a lab instance and verifies the contract
tools/test_adapter.py      adapter and CLI tests, with a fake client
tools/lab-host/            the scripts installed on a lab instance
tools/test_lab_host.sh     tests those scripts with mocked system commands
```

Three suites, none of which touch EduCloud:

```bash
python3 tools/test_safety.py    # the loop and its guardrails
python3 tools/test_adapter.py   # the adapter and CLI, with a fake API client
bash    tools/test_lab_host.sh  # the host scripts, with mocked findmnt/dd
```

Credentials come from the environment, never from a file in the repository:

```bash
export CS_URL=https://<portal-host>/client/api
export CS_KEY=...
export CS_SECRET=...
export LAB_SSH_KEY=~/.ssh/healer-lab-key
```

### Where things run

Only the healer instance has a port forward from the gateway. It sits on the
isolated network, so it reaches the other lab instances directly. The loop
therefore runs on the healer instance, and the laptop only ever talks to the
healer. This is also why the SSH firewall rule is scoped to one VPN address.

### Experiment resets

Resets redeploy a fresh instance from the clean template rather than reverting
a snapshot. Not because of the snapshot quota: two retained snapshots can be
reverted any number of times. The reason is isolation and reproducibility. A
fresh instance starts from a known identity and a known disk, so runs cannot
contaminate each other. The retained snapshot stays as an independent recovery
reference.

### Safety rules enforced in the adapter

Destructive actions are guarded where they are called, not only in the CLI:

- the target must appear in `lab_instances`
- the target may never be the healer instance
- the instance must belong to the configured project

Ownership fails closed: a project id must be configured and the instance's
`projectid` must match it exactly. Missing metadata is refused, not assumed.
Manual destruction from the CLI goes through the same checks.

High-risk actions (`reboot_instance`, `rebuild_instance`) are in the catalogue
and reachable from escalation, but the loop refuses to run them unless
`approve_high_risk=True`. It records a proposal naming the target and the
action, deduplicated, and waiting for approval does not consume the escalation
level. The level advances only when an executed repair fails verification.

Health requires every required probe to be readable and satisfied: the service
active, the configuration matching its reference, and the instance actually
answering an HTTP request. A unit reported as running is not evidence that the
service is serving, and an unreadable probe is unknown, never health.

An unexplained host key change is reported and stops the wait. The instance id
seen at each address is persisted, so a fresh process can tell a new instance
at a reused address (expected) from the same instance presenting a new key
(needs console verification).

### How the failure is made deterministic

Stock nginx does not go down when its log filesystem fills. It keeps serving,
and a reload whose configuration cannot be applied is rolled back so the
running configuration stays live (nginx.org/en/docs/control.html). A full disk
alone therefore establishes no outage, and claiming otherwise would be
reporting the simulation as if it were observed behaviour.

So the lab host declares an explicit **startup storage requirement**: an
`ExecStartPre` preflight that refuses to start nginx with less than 25 MiB free
on the bounded log volume. The experiment's maintenance operation is a
deliberate **restart**, not a reload. That makes the chain deterministic:

```
fault    rotation policy removed, producer appending to the log volume
error    the bounded log volume fills
failure  the next deliberate restart fails its preflight, nginx stops,
         and /healthz stops answering
```

The preflight is a lab protocol modelling a real startup storage requirement.
The report must describe it that way, never as stock nginx behaviour. The
installer proves the mechanism works before declaring the host ready: it fills
the volume, confirms the restart fails, reclaims the space and confirms
recovery.

The producer models a broken-rotation condition, not normal traffic. It stands
down while the rotation policy exists, so repairing the cause stops it. A
frequent rotation timer checks the size-triggered policy every 15 seconds,
because restoring a policy that is only evaluated daily would not actually
rotate anything during an experiment. Audit logs are named `healer-*.audit`
rather than `*.log`, so the distribution's own nginx rotation policy cannot
rotate them behind the experiment's back.

### What counts as available

The health probe requests the configured endpoint (`/healthz`) and checks its
body, not the root. A default root page can answer 200 while the endpoint under
test is broken.

### Injection is verified, not assumed

Starting the generator's timer proves scheduling, not that the fault took hold.
`inject("disk_leak")` watches the bounded volume until it has measurably filled
and returns `(ok, detail)`. The generator reports a full volume as the intended
outcome and any other write failure distinctly, so a permission problem cannot
be mistaken for a successful fault.

### Which volume may be flooded

One fail-closed validator, `tools/lab-host/healer-mount-guard`, is used by the
installer before anything destructive, by the service preflight, and by the
fault generator on every invocation. The adapter enforces the same rule over
SSH. A second, weaker copy of the rule is how a root-backed bind mount ends up
being written to.

Six conditions must all hold: the log directory is its own mount point and is
not root, it is on a different device from root (so a bind mount is refused),
its source is not root's source, its filesystem type matches, its size is
within the configured bound, and it is loop backed by the expected image.

### What counts as healthy, exactly

The health body must match exactly after normalising whitespace. A substring
test would accept a body of "broken" as healthy when the expected body is
"ok".

### Platform notes worth keeping in the report

- The lab image reports cloud-init as "degraded done" because of recoverable
  DHCP lease warnings, so readiness is judged by API state plus a successful
  SSH login, not by a strict cloud-init exit code.
- A snapshot record left in Error state blocks a later restore, and it can only
  be deleted while the instance is running. Start, delete the record, stop,
  then revert.
- The image is not dynamically scalable, so a capacity repair needs the
  instance stopped before the offering changes.
- API list calls return nothing unless they are scoped with the project id.
