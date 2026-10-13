"""Turn a live experiment's results.csv into docs/results.md.

    python3 tools/summarise_experiment.py evidence/experiment-<time>

Every figure is computed from the CSV, and every row links to its run folder,
so the report never contains a number that was typed by hand.
"""

import csv
import os
import statistics
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fmt(values, unit="s"):
    values = [v for v in values if v is not None]
    if not values:
        return "n/a"
    if len(values) == 1:
        return f"{values[0]:g} {unit}"
    return (f"{statistics.mean(values):.1f} {unit} "
            f"(min {min(values):g}, max {max(values):g})")


def main():
    folder = sys.argv[1]
    rows = list(csv.DictReader(open(os.path.join(folder, "results.csv"))))
    num = lambda r, k: float(r[k]) if r[k] not in ("", "None") else None
    yes = lambda r, k: r[k] == "True"
    reps = sorted({r["rep"] for r in rows})

    out = ["# Results: live A/B/C experiment on EduCloud", "",
           f"Source: `{os.path.relpath(folder, HERE)}/results.csv`, "
           f"{len(rows)} fault runs, {len(reps)} repetition(s) per configuration.", "",
           "Protocol per block (one configuration, one repetition): app-1 is reset to a "
           "fresh instance from the clean template and provisioned, Knowledge starts "
           "empty, the loop starts in that configuration, then the disk fault is "
           "injected twice (first occurrence, then repeat). In every run the "
           "deliberate maintenance restart happens 150 s after injection, whatever "
           "the loop is doing. Downtime is measured by the experiment itself, one "
           "request to `/healthz` per second, not by the loop.", "",
           "## Downtime per configuration", "",
           "| Config | Occurrence | Downtime | Ended down | Prevented | Healed | First loop action after injection | Peak log volume use |",
           "|---|---|---|---|---|---|---|---|"]
    for config in ("A", "B", "C"):
        for occ in ("first", "repeat"):
            sel = [r for r in rows if r["config"] == config and r["occurrence"] == occ]
            if not sel:
                continue
            out.append(
                f"| {config} | {occ} | {fmt([num(r, 'downtime_s') for r in sel])} | "
                f"{sum(yes(r, 'ended_down') for r in sel)}/{len(sel)} | "
                f"{sum(yes(r, 'prevented') for r in sel)}/{len(sel)} | "
                f"{sum(yes(r, 'healed') for r in sel)}/{len(sel)} | "
                f"{fmt([num(r, 'first_loop_action_s') for r in sel])} | "
                f"{fmt([num(r, 'max_disk_percent') for r in sel], '%')} |")
    out += ["", "In config A the service stays down until the experiment's own clean-up "
            "at the end of the measurement window, so its downtime is bounded by the "
            "window, not by any recovery.", "",
            "## Fresh-instance reset (template)", ""]
    resets = [num(r, "reset_s") for r in rows if r["occurrence"] == "first"]
    provs = [num(r, "provision_s") for r in rows if r["occurrence"] == "first"]
    out += [f"- Template rebuild until SSH answers: {fmt(resets)}",
            f"- Provisioning (installer with fill proof, exporters): {fmt(provs)}",
            f"- Total per reset: {fmt([a + b for a, b in zip(resets, provs) if a and b])}",
            "", "## Every run", "",
            "| Rep | Config | Occurrence | Downtime (s) | Restart ok | Prevented | Healed | Run folder |",
            "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['rep']} | {r['config']} | {r['occurrence']} | {r['downtime_s']} | "
                   f"{r['restart_ok']} | {r['prevented']} | {r['healed']} | "
                   f"[{os.path.basename(r['run'])}](../{r['run']}) |")
    path = os.path.join(HERE, "docs", "results.md")
    with open(path, "w") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
