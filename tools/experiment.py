"""Runs the experiment: configurations A, B and C against the same faults.

Every run is scripted, so ten runs cost no more effort than one. That is the
only way the experiment fits in the time budget, and it is also what makes
the results reproducible.

Output: a summary table on screen and a CSV in results/ for the report.

Run:  python3 tools/experiment.py --runs 10
"""

import argparse
import csv
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapek.loop import Healer          # noqa: E402
from mapek.world import SimulatedWorld  # noqa: E402


FAULTS = ["service_stop", "disk_leak", "config_drift"]
CONFIGS = ["A", "B", "C"]
TICKS = 40
MAINTENANCE_TICK = 20   # a routine reload, the moment a latent fault surfaces


def occurrence(healer, world, fault):
    """One occurrence: inject, run, and perform a routine reload part way.

    The restart matters for the disk fault. A full log filesystem does not stop
    a running service by itself. On the lab host the service declares a startup
    storage requirement, so the next deliberate restart fails while the volume
    is full. The restart is part of the protocol, not of the healer.
    """
    world.inject(fault)
    healer.run(MAINTENANCE_TICK)
    world.maintenance_restart()
    healer.run(TICKS - MAINTENANCE_TICK)


def single_run(config, fault, repeat_fault=False, knowledge_path=":memory:"):
    world = SimulatedWorld()
    healer = Healer(world, config=config, knowledge_path=knowledge_path)

    healer.run(3)                 # settle
    occurrence(healer, world, fault)

    first_downtime = world.downtime_ticks
    second_downtime = None

    if repeat_fault:
        before = world.downtime_ticks
        occurrence(healer, world, fault)
        second_downtime = world.downtime_ticks - before

    healed = sum(1 for e in healer.events if e.kind == "healed")
    prevented = sum(1 for e in healer.events if e.kind == "prevented")
    blocked = sum(1 for e in healer.events if e.kind == "blocked")
    escalated = sum(1 for e in healer.events if e.kind == "escalated")

    return {
        "config": config,
        "fault": fault,
        "downtime_first": first_downtime,
        "downtime_repeat": second_downtime,
        "healed": healed,
        "prevented": prevented,
        "blocked": blocked,
        "escalated": escalated,
        "recovered": world.health(world.observe(sample=False)),
    }


def no_fault_run(config):
    """Fifty quiet ticks. The loop must do nothing at all."""
    world = SimulatedWorld()
    healer = Healer(world, config=config)
    healer.run(50)
    return sum(1 for e in healer.events if e.kind in ("healed", "prevented"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    args = parser.parse_args()

    rows = []
    for config in CONFIGS:
        for fault in FAULTS:
            for _ in range(args.runs):
                rows.append(single_run(config, fault, repeat_fault=True))

    os.makedirs("results", exist_ok=True)
    out = os.path.join("results", "experiment.csv")
    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"{args.runs} runs per fault per configuration, {len(rows)} runs total")
    print(f"written to {out}\n")

    header = f"{'config':<8}{'fault':<16}{'downtime 1st':>14}{'downtime repeat':>18}{'recovered':>12}"
    print(header)
    print("-" * len(header))
    for config in CONFIGS:
        for fault in FAULTS:
            sel = [r for r in rows if r["config"] == config and r["fault"] == fault]
            first = statistics.mean(r["downtime_first"] for r in sel)
            repeat = statistics.mean(r["downtime_repeat"] for r in sel)
            rec = sum(1 for r in sel if r["recovered"]) / len(sel) * 100
            print(f"{config:<8}{fault:<16}{first:>14.1f}{repeat:>18.1f}{rec:>11.0f}%")

    print("\nFalse action check, 50 ticks with no fault injected:")
    for config in CONFIGS:
        print(f"  config {config}: {no_fault_run(config)} actions taken (target 0)")

    print("\nReading the table:")
    print("  A against B  shows what self-healing is worth")
    print("  B against C  shows what the knowledge stage adds")
    print("  the repeat column is sub-question 3: does it learn?")


if __name__ == "__main__":
    main()
