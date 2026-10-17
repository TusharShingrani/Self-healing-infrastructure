# Demo: one real gateway, one bounded repair

## Explain the service

“This real HAProxy gateway forwards HTTP requests. During a peak, outgoing connections exhaust a deliberately small source-port pool in its isolated namespace. A separate host sees actual transaction failures. The healer increases only that approved pool, verifies fresh transactions under continuing load, and later restores baseline without restarting HAProxy.”

The banking peak is motivation; the upstream is a bounded test instrument. No payments, customer data, attack emulation or 50,000-RPS claim is involved.

## Screens

Open the SSH-tunnelled console at localhost:8085 and sign in with the private operator token file. Use Grafana dashboard **HAProxy gateway - MAPE-K recovery**, UID platform-mapek, in a recent relative time window. Show independent client success, backend errors, allocation errno, pool occupancy/range, incidents, verification, modes and lease state.

## Reproducible comparison

On the management host in the checkout run `python3 experiments/gateway_study.py`. It creates two reviewed qualification incidents, explicitly promotes their procedure, then runs a seeded ordering of three observe-only, three reviewed and three automatic trials. Each uses the same bounded 24-second/64-connection background load from probe-1. Scripted approval after two seconds is a declared laboratory protocol, not real operator response-time measurement. Separate nonce transactions measure useful client recovery; cancelled background holds are not business transaction failures.

The script proves no new approval on the automatic recurrence, no gateway identity restart, no host port-range change, rollback between trials, and no tuning when the upstream alone is unavailable. Detailed evidence remains private under ~/.local/state/platform-healer/evidence and must be copied off-platform.

## Manual video

Do not run a manual demonstration concurrently with the automated study. Begin at idle with range 40000-40031 and zero active backend connections. An administrator on probe-1 starts the bounded load, using the same systemd-run invocation shown in experiments/gateway_study.py. The console cannot execute arbitrary shell commands.

1. Set **Require approval**, supply your name and a reason. Show the independent client's failing transactions and two correlated diagnostic observations.
2. Inspect the incident: healthy upstream, actual namespace EADDRNOTAVAIL, new HAProxy backend/5xx failures, exact namespace identity and approved range. Show the unchanged range before approval.
3. Approve. Show range size 256, three distinct independent successful checks and a **verified** outcome while background connections remain active. HAProxy's identity stays the same.
4. Let bounded load finish. Show zero active connections and baseline rollback after the lease expires. Wait out cooldown before another run.
5. Demonstrate two verified reviewed occurrences followed by explicit promotion, then **Use validated procedures**. A matching recurrence repairs without another approval. Use **Suspend automatic reuse** to revoke that permission.
6. Stop only the owned upstream service as an administrator. Show dependency diagnosis and no executable repair/range change, then restore it. Unknown failures need investigation, not a blind restart or blind tuning.

Observe mode executes nothing, including already approved proposals. Changing mode never cancels safe reconciliation of an existing lease. Automatic mode never manufactures a new repair or bypasses root policy. A new process/configuration/namespace scope needs fresh qualification.

## Honest interpretation

This demonstrates scoped procedural learning and closed-loop verification. It does not train an LLM, prevent every recurrence, fix a leak's source, or prove enterprise high availability. Failure to recover or a refused change is evidence to preserve, not a reason to suppress a safety check. Earlier fixture and I/O results are historical/regression evidence, not gateway comparison results.
