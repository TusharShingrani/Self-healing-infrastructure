"""Generates the Grafana dashboard, laid out along the MAPE-K loop.

    python3 monitoring/build_dashboard.py   ->  monitoring/grafana/dashboards/selfheal.json

Rows, top to bottom, follow the loop: the managed element, then what Monitor
sees, what Analyse and Plan decided, what Execute did, and what Knowledge has
learned. Annotations mark every loop event on every time series panel.
"""

import json
import os

PROM = {"type": "prometheus", "uid": "prometheus"}
panels, y, pid = [], 0, 0


def nid():
    global pid
    pid += 1
    return pid


def row(title):
    global y
    panels.append({"type": "row", "title": title, "id": nid(), "collapsed": False,
                   "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}})
    y += 1


def panel(kind, title, targets, w, h, x, desc="", unit=None, extra=None,
          mappings=None, thresholds=None, minv=None, maxv=None):
    p = {"type": kind, "title": title, "id": nid(), "datasource": PROM,
         "description": desc,
         "gridPos": {"h": h, "w": w, "x": x, "y": y},
         "targets": [{"datasource": PROM, "expr": e, "legendFormat": l,
                      "refId": chr(65 + i), **({"instant": True} if kind in ("stat", "table") else {})}
                     for i, (e, l) in enumerate(targets)],
         "fieldConfig": {"defaults": {}, "overrides": []}, "options": {}}
    d = p["fieldConfig"]["defaults"]
    if unit:
        d["unit"] = unit
    if minv is not None:
        d["min"] = minv
    if maxv is not None:
        d["max"] = maxv
    if mappings:
        d["mappings"] = mappings
    if thresholds:
        d["thresholds"] = {"mode": "absolute", "steps": thresholds}
        d["color"] = {"mode": "thresholds"}
    if kind == "timeseries":
        d["custom"] = {"lineWidth": 2, "fillOpacity": 10, "showPoints": "never"}
    if kind == "stat":
        p["options"] = {"colorMode": "background", "graphMode": "none",
                        "textMode": "value_and_name", "justifyMode": "center",
                        "reduceOptions": {"calcs": ["lastNotNull"]}}
    if kind == "state-timeline":
        p["options"] = {"showValue": "never", "mergeValues": True,
                        "rowHeight": 0.8}
    if extra:
        p.update(extra)
    panels.append(p)
    return p


UPDOWN = [{"type": "value", "options": {
    "0": {"text": "DOWN", "color": "red"}, "1": {"text": "UP", "color": "green"}}}]
OKBAD = [{"type": "value", "options": {
    "0": {"text": "NO", "color": "red"}, "1": {"text": "YES", "color": "green"}}}]
RG = [{"color": "red", "value": None}, {"color": "green", "value": 1}]

# ------------------------------------------------------------------ overview
row("Overview: is the infrastructure serving, and what is the loop doing")
panel("stat", "Service as a user sees it (/healthz)",
      [('probe_success{job="healthz"}', "{{node}}")], 6, 4, 0,
      "Blackbox request from the monitor instance. The body must be exactly ok.",
      mappings=UPDOWN, thresholds=RG)
panel("stat", "Loop health verdict",
      [("healer_loop_healthy", "{{node}}")], 6, 4, 6,
      "The loop's own verdict: every required probe readable and satisfied.",
      mappings=UPDOWN, thresholds=RG)
panel("stat", "Loop configuration",
      [("healer_loop_info", "{{node}}: config {{config}}")], 6, 4, 12,
      "A: monitor only. B: reactive healing. C: healing plus knowledge.",
      extra={"options": {"colorMode": "none", "graphMode": "none",
                         "textMode": "name", "reduceOptions": {"calcs": ["lastNotNull"]}}})
panel("stat", "Pending human approvals",
      [("sum(healer_loop_pending_approvals) or vector(0)", "approvals"),
       ("sum(healer_advisor_pending) or vector(0)", "LLM advice")], 6, 4, 18,
      "High-risk actions and LLM advice wait here until a person decides.",
      thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 1}])
y += 4
panel("state-timeline", "Availability over time",
      [('probe_success{job="healthz"}', "{{node}} /healthz"),
       ("healer:nginx_active", "{{node}} nginx unit")], 24, 6, 0,
      mappings=UPDOWN, thresholds=RG)
y += 6

# ----------------------------------------------------------- managed element
row("Monitor: what the loop observes (input to the M in MAPE-K)")
panel("timeseries", "Bounded log volume used (%)",
      [("healer:log_volume_used_percent", "{{node}}")], 8, 8, 0,
      "The 512 MiB audit log volume. The disk fault fills it.", unit="percent",
      minv=0, maxv=100,
      thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 80},
                  {"color": "red", "value": 95}],
      extra={"fieldConfig": {"defaults": {"unit": "percent", "min": 0, "max": 100,
             "custom": {"lineWidth": 2, "fillOpacity": 10, "showPoints": "never",
                        "thresholdsStyle": {"mode": "line"}},
             "thresholds": {"mode": "absolute", "steps": [
                 {"color": "green", "value": None}, {"color": "orange", "value": 80},
                 {"color": "red", "value": 95}]}}, "overrides": []}})
panel("timeseries", "Log volume growth (points per minute)",
      [("healer:log_volume_growth_percent_per_minute", "{{node}}")], 8, 8, 8,
      "The early sign. Config C learns to act on this before the service fails.")
panel("timeseries", "nginx requests per second",
      [("rate(nginx_http_requests_total[1m])", "{{node}}")], 8, 8, 16, unit="reqps")
y += 8
panel("state-timeline", "Lab facts (healer_* from the textfile collector)",
      [("healer_config_correct", "{{node}} config matches reference"),
       ("healer_rotation_policy_present", "{{node}} rotation policy present"),
       ("healer_log_mount_ok", "{{node}} log mount guard")], 12, 7, 0,
      mappings=OKBAD, thresholds=RG)
panel("state-timeline", "Symptoms named by Monitor",
      [("healer_loop_symptom == 1", "{{node}} {{symptom}}")], 12, 7, 12,
      "A symptom is an observation, not a cause. Analyse turns these into a cause.",
      mappings=[{"type": "value", "options": {"1": {"text": "present", "color": "orange"}}}])
y += 7

# ------------------------------------------------------------ analyse / plan
row("Analyse and Plan: diagnosis, escalation level, where the diagnosis came from")
panel("table", "Current diagnosis",
      [("healer_loop_diagnosis_info == 1", "")], 12, 6, 0,
      "source is rules, knowledge (recalled from an earlier incident) or llm.",
      extra={"transformations": [{"id": "labelsToFields", "options": {}},
             {"id": "organize", "options": {"excludeByName": {
                 "Time": True, "Value": True, "__name__": True, "job": True,
                 "instance": True}}}]})
panel("timeseries", "Escalation level per node",
      [("healer_loop_escalation_level", "{{node}}")], 12, 6, 12,
      "0 is the guest-level repair. Higher levels (reboot, rebuild) need approval.",
      extra={"fieldConfig": {"defaults": {"custom": {"drawStyle": "line",
             "lineInterpolation": "stepAfter", "lineWidth": 2, "fillOpacity": 10,
             "showPoints": "never"}, "decimals": 0}, "overrides": []}})
y += 6

# ------------------------------------------------------------------- execute
row("Execute: actions taken and whether verification passed")
panel("timeseries", "Loop events (per minute)",
      [("sum by (node, kind) (increase(healer_loop_events_total[1m]))", "{{node}} {{kind}}")],
      12, 8, 0, "healed, prevented, escalated, blocked, observed.",
      extra={"fieldConfig": {"defaults": {"custom": {"drawStyle": "bars",
             "fillOpacity": 60, "lineWidth": 1, "stacking": {"mode": "normal"}}},
             "overrides": []}})
panel("table", "Actions executed (total)",
      [("sum by (node, action, result) (healer_loop_actions_total)", "")], 12, 8, 12,
      extra={"transformations": [{"id": "labelsToFields", "options": {}},
             {"id": "organize", "options": {"excludeByName": {"Time": True}}}]})
y += 8
panel("timeseries", "Time spent in each MAPE stage, last tick",
      [("healer_loop_stage_seconds", "{{node}} {{stage}}")], 12, 7, 0, unit="s",
      desc="Monitor, Analyse, Plan, Execute. Execute includes verification.")
panel("stat", "Downtime ticks seen by the loop",
      [("healer_loop_downtime_ticks_total", "{{node}}")], 12, 7, 12,
      thresholds=[{"color": "green", "value": None}, {"color": "red", "value": 1}])
y += 7

# ----------------------------------------------------------------- knowledge
row("Knowledge: what the loop has learned")
panel("stat", "Incidents recorded",
      [("sum by (outcome) (healer_knowledge_incidents)", "{{outcome}}"), ("sum(healer_knowledge_incidents) or vector(0)", "total")], 8, 6, 0,
      extra={"options": {"colorMode": "value", "graphMode": "none",
                         "textMode": "value_and_name",
                         "reduceOptions": {"calcs": ["lastNotNull"]}}})
panel("stat", "Prevention rules learned",
      [('sum(healer_knowledge_rules{approved="true"}) or vector(0)', "active"),
       ('sum(healer_knowledge_rules{approved="false"}) or vector(0)', "awaiting approval")], 8, 6, 8,
      extra={"options": {"colorMode": "value", "graphMode": "none",
                         "textMode": "value_and_name",
                         "reduceOptions": {"calcs": ["lastNotNull"]}}})
panel("stat", "Knowledge used",
      [('sum(healer_loop_events_total{kind="prevented"}) or vector(0)', "failures prevented"),
       ('sum(healer_loop_diagnoses_total{source="knowledge"}) or vector(0)', "diagnoses recalled"),
       ('sum(healer_loop_diagnoses_total{source="llm"}) or vector(0)', "diagnoses from approved LLM advice")],
      8, 6, 16,
      extra={"options": {"colorMode": "value", "graphMode": "none",
                         "textMode": "value_and_name",
                         "reduceOptions": {"calcs": ["lastNotNull"]}}})
y += 6

dashboard = {
    "uid": "selfheal-mapek",
    "title": "Self-healing infrastructure (MAPE-K)",
    "tags": ["mape-k", "self-healing"],
    "timezone": "browser",
    "refresh": "10s",
    "time": {"from": "now-30m", "to": "now"},
    "schemaVersion": 39,
    "editable": False,
    "annotations": {"list": [{
        "name": "Loop events", "enable": True, "datasource": PROM,
        "iconColor": "purple",
        "expr": "changes(healer_loop_events_total[20s]) > 0",
        "step": "10s", "titleFormat": "{{kind}}",
        "textFormat": "{{node}}: {{kind}} {{cause}}",
        "useValueForTime": False}]},
    "panels": panels,
}

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "grafana", "dashboards", "selfheal.json")
with open(out, "w") as fh:
    json.dump(dashboard, fh, indent=1)
print(f"wrote {out} with {len(panels)} panels")
