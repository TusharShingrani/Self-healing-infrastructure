"""The managed element: the infrastructure the loop looks after.

Adapters with the same interface:
  SimulatedWorld       runs anywhere, used for development and for testing the loop
  EduCloudWorld        a real lab instance (see educloud.py)
  InfrastructureWorld  the two-VM dependency stack (see infrastructure.py)

Interface contract, which each must honour:

    step()                  advance time only, no probing
    observe(sample=True)    one reading. sample=False means do not update the
                            rate-of-change state, so post-action verification
                            cannot corrupt the growth measurement
    health(observation)     judge health from a reading already taken
    note_health(healthy)    downtime accounting
    effectors               restart_service, clear_logs, fix_log_rotation,
                            restore_config, reboot_instance, rebuild_instance

Observations use None for "could not be read". A failed probe must never look
like a healthy measurement.
"""


class SimulatedWorld:
    """A fake host. One tick is one unit of time."""

    def __init__(self, service="web", disk_start=40.0):
        self.service = service
        self.service_running = True
        self.disk_percent = disk_start
        self.disk_growth = 0.2
        self.log_rotation_broken = False
        self.config_correct = True
        self.reachable = True
        self.tick_count = 0
        self.downtime_ticks = 0
        self.reboots = 0
        self.rebuilds = 0

    # ---------------------------------------------------------------- probes

    def observe(self, sample=True):
        if not self.reachable:
            return {
                "tick": self.tick_count, "reachable": False,
                "service_running": None, "disk_percent": None,
                "disk_growth": None, "config_correct": None,
            }
        return {
            "tick": self.tick_count,
            "reachable": True,
            "service_running": self.service_running,
            "disk_percent": round(self.disk_percent, 1),
            "disk_growth": round(self.disk_growth, 2),
            "config_correct": self.config_correct,
        }

    def health(self, observation):
        if not observation.get("reachable"):
            return False
        return bool(observation.get("service_running")) and \
            bool(observation.get("config_correct"))

    def note_health(self, healthy):
        if not healthy:
            self.downtime_ticks += 1

    # -------------------------------------------------------------- effectors

    def restart_service(self):
        if not self.config_correct:
            return False, "configuration invalid, service refuses to start"
        if self.disk_percent >= 99:
            return False, "log filesystem full, service refuses to start"
        self.service_running = True
        return True, "service restarted"

    def clear_logs(self):
        freed = min(self.disk_percent - 20, 45)
        self.disk_percent = max(20.0, self.disk_percent - freed)
        return True, f"reclaimed {freed:.0f}% of the log filesystem"

    def fix_log_rotation(self):
        self.log_rotation_broken = False
        self.disk_growth = 0.2
        return True, "log rotation restored"

    def restore_config(self):
        self.config_correct = True
        return True, "configuration restored from reference"

    def reboot_instance(self):
        self.reachable = True
        self.service_running = True
        self.reboots += 1
        return True, "instance rebooted"

    def rebuild_instance(self):
        self.__init__(self.service)
        self.rebuilds += 1
        return True, "instance rebuilt from the clean template"

    # ---------------------------------------------------- fault injection

    def inject(self, fault):
        """Experiment only. Never part of the healer."""
        if fault == "service_stop":
            self.service_running = False
        elif fault == "disk_leak":
            self.log_rotation_broken = True
            self.disk_growth = 6.0
        elif fault == "config_drift":
            self.config_correct = False
            self.service_running = False      # models the deliberate restart protocol
        elif fault == "unreachable":
            self.reachable = False
        else:
            raise ValueError(f"unknown fault: {fault}")

    def maintenance_restart(self):
        """The lab's defined maintenance operation: a deliberate restart.

        A restart rather than a reload, because the real host declares a
        startup storage requirement that a restart must satisfy. Keeping the
        simulated and real semantics aligned matters: the simulation must not
        model behaviour the platform does not have.
        """
        ok, _ = self.restart_service()
        if not ok:
            self.service_running = False
        return ok

    # ------------------------------------------------------------------ time

    def step(self):
        self.tick_count += 1
        self.disk_percent = min(100.0, self.disk_percent + self.disk_growth)
