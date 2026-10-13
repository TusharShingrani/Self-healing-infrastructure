"""The MAPE-K loop as a long-running service on the healer instance.

    python3 tools/healer_service.py            (normally run by systemd, see tools/start_loop.sh)

One Healer per managed instance, all sharing one Knowledge database, so what
the loop learns on app-1 is available on app-2. Monitor reads Prometheus;
Execute verifies with direct probes. Every loop event is appended to
state/events.jsonl and published as metrics on :9105 for Grafana.

Environment (all optional except the credentials):
    CS_URL CS_KEY CS_SECRET LAB_SSH_KEY   platform and SSH access
    HEALER_CONFIG     A | B | C           default C
    HEALER_NODES      app-1,app-2         default: lab_instances from config/lab.json
    HEALER_INTERVAL   seconds per tick    default 10
    HEALER_METRICS    address:port        default <healer_guest_ip>:9105
    HEALER_STATE      directory           default <repo>/state

Human controls, read every tick (no restart needed):
    state/approve-high-risk   if this file exists, reboot/rebuild proposals may run
    state/paused              if this file exists, the loop observes but does not act
                              (used while an experiment injects faults by hand)
"""

import json
import os
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from mapek.advisor import Advisor                                # noqa: E402
from mapek.cloudstack import CloudStack, CloudStackError         # noqa: E402
from mapek.educloud import EduCloudWorld, load_lab               # noqa: E402
from mapek.knowledge import Knowledge                            # noqa: E402
from mapek.loop import Healer                                    # noqa: E402
from mapek.prometheus import PrometheusSource                    # noqa: E402

SYMPTOMS = ["unreachable", "service_down", "disk_high", "disk_critical",
            "disk_growing_fast", "config_drift", "probe_failed"]


class Node:
    def __init__(self, name, healer):
        self.name = name
        self.healer = healer
        self.ticks = 0
        self.tick_errors = 0
        self.last_tick = 0.0
        self.last_error = ""
        self.events_by_kind = {}         # (kind, cause) -> count


class Service:
    def __init__(self):
        self.lab = load_lab()
        self.config = os.environ.get("HEALER_CONFIG", "C").upper()
        self.interval = float(os.environ.get("HEALER_INTERVAL", "10"))
        names = os.environ.get("HEALER_NODES")
        self.node_names = names.split(",") if names else list(self.lab["lab_instances"])
        self.state = os.environ.get("HEALER_STATE", os.path.join(HERE, "state"))
        os.makedirs(self.state, exist_ok=True)
        self.db_path = os.path.join(self.state, "knowledge.db")
        self.events_path = os.path.join(self.state, "events.jsonl")
        self.lock = threading.Lock()
        self.stopping = threading.Event()

        cs = CloudStack(project=self.lab["project_id"])
        prom = PrometheusSource(self.lab["prometheus_url"])
        self.knowledge = Knowledge(self.db_path)       # for metrics and advice
        self.advisor = Advisor(Knowledge(self.db_path))
        self.nodes = []
        for name in self.node_names:
            if name not in self.lab["lab_instances"]:
                raise SystemExit(f"{name} is not in lab_instances, refusing to manage it")
            world = EduCloudWorld(cs, name, self.lab,
                                  key_path=os.environ.get("LAB_SSH_KEY"), metrics=prom)
            healer = Healer(world, config=self.config, knowledge_path=self.db_path)
            if self.config != "A":
                healer.advisor = self.advisor
            node = Node(name, healer)
            healer.on_event = lambda event, node=node: self._record(node, event)
            self.nodes.append(node)

    # -------------------------------------------------------------- events

    def _record(self, node, event):
        diagnosis = node.healer.diagnosis
        line = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "node": node.name, "config": self.config, "tick": event.tick,
            "kind": event.kind, "cause": event.cause, "level": event.level,
            "source": diagnosis.source if diagnosis else "",
            "symptoms": event.symptoms, "actions": event.actions,
            "detail": event.detail,
            "monitor_source": node.healer.last_observation.get("monitor_source", ""),
        }
        key = (event.kind, event.cause or "")
        node.events_by_kind[key] = node.events_by_kind.get(key, 0) + 1
        with open(self.events_path, "a") as fh:
            fh.write(json.dumps(line) + "\n")
        print(f"{line['time']} {node.name:<6} {event.kind.upper():<10} "
              f"L{event.level} {event.cause} {event.detail}", flush=True)

    # ---------------------------------------------------------------- loop

    def run(self):
        print(f"MAPE-K loop starting: config {self.config}, nodes "
              f"{', '.join(self.node_names)}, every {self.interval:.0f}s, "
              f"advisor {'on' if self.advisor.available else 'off (requests recorded for a person)'}",
              flush=True)
        while not self.stopping.is_set():
            started = time.time()
            approve = os.path.exists(os.path.join(self.state, "approve-high-risk"))
            paused = os.path.exists(os.path.join(self.state, "paused"))
            for node in self.nodes:
                node.healer.approve_high_risk = approve
                with self.lock:
                    self._tick(node, paused)
            self.stopping.wait(max(0.0, self.interval - (time.time() - started)))

    def _tick(self, node, paused):
        healer = node.healer
        real_config = healer.config
        try:
            if paused:
                healer.config = "A"          # observe and record only
            healer.tick()
            node.ticks += 1
            node.last_error = ""
        except (CloudStackError, OSError, RuntimeError) as error:
            # The platform API or the network failed. That is an observation
            # about the healer's own reach, not a reason to stop watching.
            node.tick_errors += 1
            node.last_error = f"{type(error).__name__}: {error}"[:300]
            print(f"tick error on {node.name}: {node.last_error}", flush=True)
        finally:
            healer.config = real_config
            node.last_tick = time.time()

    # ------------------------------------------------------------- metrics

    def metrics(self):
        out = []

        def m(name, labels, value):
            text = ",".join(f'{k}="{str(v).replace(chr(34), "")}"' for k, v in labels.items())
            out.append(f"{name}{{{text}}} {value}" if text else f"{name} {value}")

        with self.lock:
            for node in self.nodes:
                h, n = node.healer, {"node": node.name}
                m("healer_loop_info", dict(n, config=h.config), 1)
                m("healer_loop_ticks_total", n, node.ticks)
                m("healer_loop_tick_errors_total", n, node.tick_errors)
                m("healer_loop_last_tick_timestamp_seconds", n, round(node.last_tick, 1))
                if h.last_healthy is not None:
                    m("healer_loop_healthy", n, int(h.last_healthy))
                for symptom in SYMPTOMS:
                    m("healer_loop_symptom", dict(n, symptom=symptom),
                      int(symptom in h.last_symptoms))
                if h.diagnosis is not None:
                    m("healer_loop_diagnosis_info",
                      dict(n, cause=h.diagnosis.cause, source=h.diagnosis.source,
                           confidence=h.diagnosis.confidence), 1)
                m("healer_loop_escalation_level", n, h.escalation_level())
                m("healer_loop_pending_approvals", n, len(h.pending_approval))
                m("healer_loop_high_risk_approved", n, int(h.approve_high_risk))
                m("healer_loop_downtime_ticks_total", n, h.world.downtime_ticks)
                for (kind, cause), count in node.events_by_kind.items():
                    m("healer_loop_events_total", dict(n, kind=kind, cause=cause), count)
                for source, count in h.diagnoses_by_source.items():
                    m("healer_loop_diagnoses_total", dict(n, source=source), count)
                for (action, result), count in h.action_counts.items():
                    m("healer_loop_actions_total", dict(n, action=action, result=result),
                      count)
                for stage, seconds in h.stage_seconds.items():
                    m("healer_loop_stage_seconds", dict(n, stage=stage), round(seconds, 4))
                source = h.last_observation.get("monitor_source")
                if source:
                    m("healer_loop_monitor_source_info", dict(n, source=source), 1)

            counts = self.knowledge.counts()
        for outcome, count in counts["incidents"].items():
            m("healer_knowledge_incidents", {"outcome": outcome}, count)
        for approved, count in counts["rules"].items():
            m("healer_knowledge_rules", {"approved": approved}, count)
        for status, count in counts["advice"].items():
            m("healer_advisor_advice", {"status": status}, count)
        m("healer_advisor_pending", {}, counts["advice"].get("pending", 0))
        m("healer_advisor_available", {}, int(self.advisor.available))
        return "\n".join(out) + "\n"


def serve_metrics(service, address):
    host, port = address.rsplit(":", 1)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/metrics":
                body, kind = service.metrics().encode(), "text/plain; version=0.0.4"
            elif self.path == "/events":
                try:
                    with open(service.events_path) as fh:
                        lines = fh.readlines()[-100:]
                except OSError:
                    lines = []
                body = ("[" + ",".join(l.strip() for l in lines) + "]").encode()
                kind = "application/json"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer((host, int(port)), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    service = Service()
    default = f"{service.lab.get('healer_guest_ip', '127.0.0.1')}:9105"
    serve_metrics(service, os.environ.get("HEALER_METRICS", default))
    signal.signal(signal.SIGTERM, lambda *a: service.stopping.set())
    signal.signal(signal.SIGINT, lambda *a: service.stopping.set())
    service.run()


if __name__ == "__main__":
    main()
