"""One live fault run against a real lab instance, measured independently.

    python3 tools/live_run.py app-1 disk_leak
    python3 tools/live_run.py app-2 disk_leak --restart-at 150 --watch 180
    python3 tools/live_run.py app-1 config_drift
    python3 tools/live_run.py app-1 service_stop

The MAPE-K loop runs separately (tools/start_loop.sh). This script is the
experimenter, not the healer:

  1. it injects the fault, and confirms the fault actually took hold
  2. at a FIXED time it performs the lab's maintenance operation, a deliberate
     restart, whatever the loop is doing. The same protocol for A, B and C
  3. it measures availability itself, with its own request to /healthz every
     second, so downtime is never judged by the system under test
  4. afterwards it restores the instance if the loop did not, and records that
     clean-up as manual, never as healing

Results go to evidence/runs/<time>-<node>-<fault>-<config>/.
"""

import argparse
import calendar
import csv
import json
import os
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from mapek.cloudstack import CloudStack                          # noqa: E402
from mapek.educloud import EduCloudWorld, load_lab               # noqa: E402
from mapek.prometheus import PrometheusSource                    # noqa: E402

DEFAULT_RESTART = {"disk_leak": 150, "config_drift": 30, "service_stop": None}


def stamp(t=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t or time.time()))


class Sampler(threading.Thread):
    """Requests /healthz every second from the healer. The ground truth."""

    def __init__(self, url, prom, node, interval=1.0):
        super().__init__(daemon=True)
        self.url, self.prom, self.node, self.interval = url, prom, node, interval
        self.rows, self.stop = [], threading.Event()
        self.last_disk = None

    def run(self):
        n = 0
        while not self.stop.is_set():
            t = time.time()
            try:
                with urllib.request.urlopen(self.url, timeout=2) as r:
                    ok = r.status == 200 and r.read(64).decode().strip() == "ok"
            except Exception:                         # noqa: BLE001
                ok = False
            if n % 5 == 0:
                reading = self.prom.query("healer:log_volume_used_percent").get(self.node)
                self.last_disk = round(reading[0], 1) if reading else None
            self.rows.append((t, ok, self.last_disk))
            n += 1
            self.stop.wait(max(0.0, self.interval - (time.time() - t)))


def loop_config():
    try:
        with urllib.request.urlopen("http://10.1.1.205:9105/metrics", timeout=3) as r:
            for line in r.read().decode().splitlines():
                if line.startswith("healer_loop_info"):
                    return line.split('config="')[1].split('"')[0]
    except Exception:                                 # noqa: BLE001
        pass
    return "loop-not-running"


def loop_events(node, since):
    path = os.path.join(HERE, "state", "events.jsonl")
    out = []
    try:
        with open(path) as fh:
            for line in fh:
                e = json.loads(line)
                if e["node"] == node and e["time"] >= stamp(since):
                    out.append(e)
    except OSError:
        pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("node")
    ap.add_argument("fault", choices=["disk_leak", "config_drift", "service_stop"])
    ap.add_argument("--restart-at", type=float, default=None,
                    help="seconds after injection for the deliberate restart")
    ap.add_argument("--watch", type=float, default=180,
                    help="seconds to keep measuring after the restart")
    ap.add_argument("--settle", type=float, default=30,
                    help="end early once healthy this long after the restart")
    args = ap.parse_args()

    lab = load_lab()
    if args.node not in lab["lab_instances"]:
        sys.exit(f"{args.node} is not a lab instance, refusing to inject faults")
    restart_at = args.restart_at if args.restart_at is not None else DEFAULT_RESTART[args.fault]

    cs = CloudStack(project=lab["project_id"])
    world = EduCloudWorld(cs, args.node, lab, key_path=os.environ.get("LAB_SSH_KEY"))
    world.observe(sample=False)                     # resolves the address and SSH
    ip = lab["addresses"][args.node]
    prom = PrometheusSource(lab["prometheus_url"])
    config = loop_config()

    started = time.time()
    run_dir = os.path.join(HERE, "evidence", "runs",
                           f"{stamp(started).replace(':', '')}-{args.node}-{args.fault}-{config}")
    os.makedirs(run_dir, exist_ok=True)
    log_lines = []

    def log(msg):
        line = f"{stamp()} +{time.time() - started:6.1f}s  {msg}"
        print(line, flush=True)
        log_lines.append(line)

    log(f"run {args.fault} on {args.node} ({ip}), loop config {config}, "
        f"deliberate restart at +{restart_at}s" if restart_at else
        f"run {args.fault} on {args.node} ({ip}), loop config {config}, no restart")

    sampler = Sampler(f"http://{ip}{lab['health_path']}", prom, args.node)
    sampler.start()
    time.sleep(3)
    if not all(ok for _, ok, _ in sampler.rows):
        log("WARNING: the instance was not healthy before the fault")

    inject_at = time.time()
    ok, detail = world.inject(args.fault)
    log(f"inject {args.fault}: {'confirmed' if ok else 'NOT confirmed'}: {detail}")

    restart = None
    if restart_at:
        wait = inject_at + restart_at - time.time()
        if wait > 0:
            log(f"waiting {wait:.0f}s for the maintenance window")
            time.sleep(wait)
        disk = sampler.last_disk
        r_ok, r_detail = world.maintenance_restart()
        restart = {"time": stamp(), "offset": round(time.time() - inject_at, 1),
                   "ok": r_ok, "detail": r_detail, "disk_percent_before": disk}
        log(f"deliberate restart: {'succeeded' if r_ok else 'FAILED'} "
            f"(log volume {disk}% used): {r_detail[:150]}")

    watch_from = time.time()
    healthy_since = None
    while time.time() - watch_from < args.watch:
        time.sleep(1)
        latest = sampler.rows[-1][1] if sampler.rows else False
        if latest:
            healthy_since = healthy_since or time.time()
            if time.time() - healthy_since >= args.settle:
                break
        else:
            healthy_since = None
    sampler.stop.set()
    sampler.join()
    log(f"measurement ended, {len(sampler.rows)} samples")

    # ---- independent summary from the samples
    rows = [(t, ok, d) for t, ok, d in sampler.rows if t >= inject_at]
    down = [t for t, ok, _ in rows if not ok]
    events = loop_events(args.node, inject_at - 1)
    kinds = [e["kind"] for e in events]
    recovered_at = None
    if down:
        after = [t for t, ok, _ in rows if ok and t > down[-1]]
        recovered_at = after[0] if after else None
    summary = {
        "node": args.node, "fault": args.fault, "loop_config": config,
        "inject": {"time": stamp(inject_at), "confirmed": ok, "detail": detail},
        "restart": restart,
        "samples": len(rows), "sample_interval_s": 1.0,
        "downtime_s": len(down),
        "first_down": stamp(down[0]) if down else None,
        "recovered": stamp(recovered_at) if recovered_at else None,
        "recovery_s_from_first_down": round(recovered_at - down[0], 1) if recovered_at else None,
        "ended_down": bool(rows) and not rows[-1][1],
        "loop_events": kinds,
        "first_loop_action_s": next((round(_t(e) - inject_at, 1) for e in events
                                     if e["kind"] in ("healed", "prevented")), None),
        "prevented": "prevented" in kinds,
        "healed": "healed" in kinds,
        "max_disk_percent": max((d for _, _, d in rows if d is not None), default=None),
    }

    # ---- clean up anything the loop did not, and say so
    cleanup = []
    if summary["ended_down"] or world.observe(sample=False).get("config_correct") is False \
            or args.fault == "disk_leak":
        for name in ("fix_log_rotation", "clear_logs", "restore_config", "restart_service"):
            if args.fault != "disk_leak" and name in ("fix_log_rotation", "clear_logs"):
                continue
            c_ok, c_detail = getattr(world, name)()
            cleanup.append({"action": name, "ok": c_ok, "detail": c_detail})
        world.stop_fault()
        log("post-run reset by the experiment, idempotent, not counted as healing: "
            + ", ".join(f"{c['action']}={'ok' if c['ok'] else 'failed'}" for c in cleanup))
    summary["manual_cleanup"] = cleanup
    summary["healthy_after_cleanup"] = world.health(world.observe(sample=False))

    with open(os.path.join(run_dir, "samples.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time_utc", "offset_s", "healthz_ok", "log_volume_used_percent"])
        for t, s_ok, d in sampler.rows:
            w.writerow([stamp(t), round(t - inject_at, 1), int(s_ok), d])
    with open(os.path.join(run_dir, "loop_events.jsonl"), "w") as fh:
        fh.writelines(json.dumps(e) + "\n" for e in events)
    with open(os.path.join(run_dir, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    with open(os.path.join(run_dir, "run.log"), "w") as fh:
        fh.write("\n".join(log_lines) + "\n")

    print(json.dumps({k: summary[k] for k in (
        "loop_config", "downtime_s", "recovery_s_from_first_down", "prevented", "healed",
        "first_loop_action_s", "max_disk_percent", "ended_down", "healthy_after_cleanup")},
        indent=2))
    print(f"evidence: {os.path.relpath(run_dir, HERE)}")


def _t(event):
    return calendar.timegm(time.strptime(event["time"], "%Y-%m-%dT%H:%M:%SZ"))


if __name__ == "__main__":
    main()
