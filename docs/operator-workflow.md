# Incident diagnosis, operator review and validated procedures

The managed elements remain Ubuntu VMs running nginx, not containers.
The running service now defaults to incident review (`HEALER_REVIEW=1`).
Simulation tests still use the old ungated mode unless an Operator is attached.
Original A/B/C measurements remain historical results of the earlier policy.

## Personally operate it

On the healer:

```bash
cd ~/projects/selfheal
python3 tools/lab_shell.py
python3 tools/incidents.py list
python3 tools/incidents.py show 1
```

Use the actual id in the list. `show` names the VM id/address, nginx,
configuration path, log mount and rotation policy. It includes nginx's
configuration-test diagnostic (including the failing file and line), service
state and exit status, disk/mount evidence, configuration hashes, proposed
catalogue actions, risk and verification conditions. Diagnosis remains a
hypothesis; a config mismatch alone does not identify who changed it.

Approve one proposed attempt, or reject it:

```bash
python3 tools/incidents.py approve 1 --who tushar --notes 'Checked nginx error and reference; approve restoration'
python3 tools/incidents.py reject 1 --who tushar --notes 'Insufficient evidence; investigate dependency first'
```

Approval lasts 15 minutes, is single-use, and is tied to VM identity, current
evidence and proposed actions. Changed service/config evidence requires a new
review. Rejections do not reopen every tick. A cleared condition can later
create a new occurrence. The terminal account is the access boundary; `--who`
is an operator-reported audit name, not a separate authentication mechanism.

For a human repair, make the change yourself, then report what actually changed:

```bash
python3 tools/incidents.py record-human 2 --who tushar --actions restore_config --notes 'Copied reviewed reference, validated nginx config, then reloaded nginx'
```

That command performs no repair. It independently probes the target and records
success only if the required and action-specific checks pass. HTTP alone is
insufficient to certify a rotation repair. Arbitrary command strings in notes
are never executed. Manual changes must map to existing supported guest actions
to become an automatable procedure; other repairs need a reviewed adapter and
tests before they can be automated. Unknown diagnoses cannot be promoted.

## Earning autonomy

```bash
python3 tools/incidents.py procedures
python3 tools/incidents.py promote 1 --who tushar
```

A verified fix first creates a candidate. Promotion requires two distinct
verified incident occurrences plus explicit operator review. A promoted
procedure is scoped to its target, project, template, service, paths, reference
file contents, diagnosis, symptoms and action list. It is not a promise that
arbitrary future failures can be repaired. Live fresh symptoms must still match.
Failed verification revokes automatic use. Review again after adapter changes.

High-risk reboot/rebuild never become automatic procedures. Their existing
separate gate, target allowlist and ownership checks remain. Cooldown and action
rate limits still apply. No guardrail is disabled by incident approval.

The old Knowledge prevention rules and LLM advice cannot bypass this review
gate. New legacy prevention rules are no longer auto-approved by the reviewed
service. Validation of a repair is separate from validation of an early-sign
prevention policy; this change does not automatically promote prevention rules.

## MAPE-K mapping

- Monitor: Prometheus plus direct probes; non-sampling diagnostic evidence.
- Analyse: named rule/Knowledge/approved-advice hypothesis with concrete evidence.
- Plan: fixed action catalogue, persistent case, scope, risk and verification plan.
- Execute: approval or validated procedure, existing guardrails, actual effectors,
  fresh verification; the operator can instead perform and report the repair.
- Knowledge: persistent operator cases, before/after observations, reported
  changes, append-only decision audit, candidate/validated/revoked procedures.

This is a terminal operator interface. It adds the workflow before a future web
console. The LLM remains advisory; it does not run free-form commands, train
itself, or promote a procedure. Evidence is bounded output from the managed
component; environment dumps, private keys and secret values are not collected.

## Demonstration and evidence boundary

`tools/demo_operator_live.py` is a scripted operator exercise on app-1. It
injects an invalid nginx directive and deliberately restarts nginx to expose
the configuration failure. It proves that the first attempt waits, an approved
repair verifies, a separate SSH repair can be recorded, two verified occurrences
can be promoted, and a third occurrence can use the validated procedure. The
script plays the operator role; it is not evidence of a person using the CLI.

It preserves earlier Knowledge and honours cooldown at ten seconds per tick.
The legacy loop is paused during the exercise, and the config is restored in
cleanup. Review and preserve failures as well as successes. The first pilot
correctly invalidated approval when service evidence changed; the final
exercise uses the same deliberate restart protocol for all three occurrences.
