"""Prometheus as the sensor layer for the Monitor stage.

The loop asks Prometheus for the latest value of each series, per node. A value
is only used if it is fresh: Prometheus keeps returning the last sample for a
while after a target stops reporting, and a stale "up" is exactly the kind of
reading that makes automation confidently wrong. Anything missing or stale
comes back as None, and the adapter falls back to a direct probe.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request


# observation field -> (PromQL, how to turn the value into the field)
SERIES = {
    "http_ok":         ('probe_success{job="healthz"}', lambda v: v == 1.0),
    "service_running": ("healer:nginx_active", lambda v: v == 1.0),
    "disk_percent":    ("healer:log_volume_used_percent", lambda v: round(v, 1)),
    "disk_growth":     ("healer:log_volume_growth_percent_per_minute", lambda v: round(v, 2)),
    "config_correct":  ("healer_config_correct", lambda v: v == 1.0),
}

# The healer-* facts are written by a 15 s timer on the host and scraped every
# 10 s, so they can legitimately be up to ~25 s old. Older than this is stale.
FACT_AGE_LIMIT = 45


class PrometheusSource:
    def __init__(self, url, timeout=5, max_age=30, clock=time.time, opener=None):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.max_age = max_age
        self.clock = clock
        self._open = opener or urllib.request.urlopen
        self.last_error = ""

    def query(self, expr):
        """Instant query. Returns {node: (value, sample_time)}, {} on failure."""
        url = f"{self.url}/api/v1/query?" + urllib.parse.urlencode({"query": expr})
        try:
            with self._open(url, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode())
        except (urllib.error.URLError, OSError, ValueError) as error:
            self.last_error = f"prometheus unreachable: {error}"
            return {}
        if payload.get("status") != "success":
            self.last_error = f"prometheus query failed: {payload.get('error')}"
            return {}
        out = {}
        for item in payload["data"]["result"]:
            node = item["metric"].get("node")
            stamp, raw = item["value"]
            try:
                out[node] = (float(raw), float(stamp))
            except ValueError:
                continue
        return out

    def observe(self, node, newer_than=0.0):
        """Fresh readings for one node. Missing or stale fields are absent.

        newer_than: ignore samples taken before this time. After the loop acts
        on an instance, a sample scraped before the action describes the world
        as it was, and acting on it would repeat a repair that already worked.
        """
        now = self.clock()
        readings, stale = {}, []
        facts_fresh = self._facts_fresh(node, now, newer_than)
        for field, (expr, convert) in SERIES.items():
            result = self.query(expr).get(node)
            if result is None:
                continue
            value, stamp = result
            if now - stamp > self.max_age or stamp < newer_than:
                stale.append(field)
                continue
            if field == "config_correct" and not facts_fresh:
                stale.append(field)
                continue
            if value != value:          # NaN, e.g. deriv over too few samples
                continue
            readings[field] = convert(value)
        return readings, stale

    def _facts_fresh(self, node, now, newer_than=0.0):
        # the value of this series is the time the host measured the facts
        result = self.query("healer_metrics_timestamp_seconds").get(node)
        return (bool(result) and now - result[0] <= FACT_AGE_LIMIT
                and result[0] >= newer_than)
