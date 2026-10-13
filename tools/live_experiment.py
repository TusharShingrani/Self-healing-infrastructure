"""The live A/B/C experiment on EduCloud.

    python3 tools/live_experiment.py --reps 3                   full run, about 15 min per block
    python3 tools/live_experiment.py --reps 1 --configs C --no-reset

For every repetition and configuration (a "block"):

  1. stop the loop
  2. reset app-1 to a fresh instance from the clean template, and time it
     (lab.py reset, then tools/provision.sh), unless --no-reset
  3. archive the Knowledge database, so the block starts knowing nothing
  4. start the loop in that configuration, managing app-1 only
  5. run the disk fault twice (first occurrence, then repeat) with
     tools/live_run.py, which measures /healthz independently every second

Results: evidence/experiment-<time>/results.csv plus every run's own folder.
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = "app-1"


def stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sh(cmd, log, env=None, check=True):
    log.write(f"\n$ {cmd}\n")
    log.flush()
    started = time.time()
    proc = subprocess.run(cmd, shell=True, cwd=HERE, text=True, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.write(proc.stdout)
    log.write(f"[exit {proc.returncode} after {time.time() - started:.0f}s]\n")
    log.flush()
    if check and proc.returncode != 0:
        raise RuntimeError(f"{cmd} failed with {proc.returncode}")
    return proc, time.time() - started


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--configs", default="A,B,C")
    ap.add_argument("--no-reset", action="store_true")
    args = ap.parse_args()

    out = os.path.join(HERE, "evidence", f"experiment-{stamp().replace(':', '')}")
    os.makedirs(out)
    log = open(os.path.join(out, "experiment.log"), "w")
    rows = []
    env = dict(os.environ, HEALER_NODES=NODE)
    print(f"experiment folder: {os.path.relpath(out, HERE)}", flush=True)

    for rep in range(1, args.reps + 1):
        for config in args.configs.split(","):
            block = f"rep {rep} config {config}"
            print(f"{stamp()} {block}: start", flush=True)
            sh("bash tools/start_loop.sh stop", log, env, check=False)

            reset_s = provision_s = None
            if not args.no_reset:
                proc, reset_s = sh(f"python3 tools/lab.py reset {NODE}", log, env)
                _, provision_s = sh(
                    f"bash tools/provision.sh app {json.load(open('config/lab.json'))['addresses'][NODE]}"
                    f" {os.path.relpath(out, HERE)}/provision-{rep}-{config}.log", log, env)
                print(f"{stamp()} {block}: template reset {reset_s:.0f}s, "
                      f"provision {provision_s:.0f}s", flush=True)

            db = os.path.join(HERE, "state", "knowledge.db")
            if os.path.exists(db):
                shutil.move(db, os.path.join(out, f"knowledge-before-{rep}-{config}.db"))
            sh(f"bash tools/start_loop.sh start {config}", log, env)
            time.sleep(40)                  # Prometheus windows fill with healthy data

            for occurrence in ("first", "repeat"):
                proc, _ = sh(f"python3 -u tools/live_run.py {NODE} disk_leak", log, env)
                # Use the folder this run reports. "The newest folder" was wrong
                # once: an unrelated run on app-2 was attributed to this block.
                line = [l for l in proc.stdout.splitlines() if l.startswith("evidence: ")]
                if not line:
                    raise RuntimeError("live_run did not report its evidence folder")
                run_dir = os.path.join(HERE, line[-1].split(": ", 1)[1].strip())
                summary_node = json.load(open(os.path.join(run_dir, "summary.json")))["node"]
                if summary_node != NODE:
                    raise RuntimeError(f"{run_dir} is a run on {summary_node}, not {NODE}")
                summary = json.load(open(os.path.join(run_dir, "summary.json")))
                if summary["loop_config"] != config:
                    # Fail closed: a run without the right loop measures nothing
                    # about this configuration. It happened once when the healer
                    # stalled; the run showed 0 s downtime with no restart at all.
                    raise RuntimeError(f"{run_dir} ran with loop {summary['loop_config']!r}, "
                                       f"not config {config}; experiment stopped")
                row = {"rep": rep, "config": config, "occurrence": occurrence,
                       "loop_config": summary["loop_config"],
                       "downtime_s": summary["downtime_s"],
                       "recovery_s": summary["recovery_s_from_first_down"],
                       "ended_down": summary["ended_down"],
                       "prevented": summary["prevented"], "healed": summary["healed"],
                       "first_loop_action_s": summary["first_loop_action_s"],
                       "max_disk_percent": summary["max_disk_percent"],
                       "restart_ok": (summary["restart"] or {}).get("ok"),
                       "reset_s": round(reset_s, 1) if reset_s else None,
                       "provision_s": round(provision_s, 1) if provision_s else None,
                       "run": os.path.relpath(run_dir, HERE)}
                rows.append(row)
                print(f"{stamp()} {block} {occurrence}: downtime {row['downtime_s']}s, "
                      f"prevented {row['prevented']}, healed {row['healed']}, "
                      f"ended down {row['ended_down']}", flush=True)
                time.sleep(40)              # let the rate window settle between runs

            shutil.copy(db, os.path.join(out, f"knowledge-after-{rep}-{config}.db")) \
                if os.path.exists(db) else None
            with open(os.path.join(out, "results.csv"), "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)

    sh("bash tools/start_loop.sh start C", dict(os.environ), check=False)
    print(f"{stamp()} done: {os.path.relpath(out, HERE)}/results.csv", flush=True)


if __name__ == "__main__":
    main()
