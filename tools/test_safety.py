"""Safety tests. These are the evidence behind every safety claim.

Run:  python3 tools/test_safety.py

No EduCloud calls are made. The platform tests use a fake client that records
what would have been called, so a destructive mistake is caught here instead of
on the real lab.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapek.actions import CATALOGUE, HIGH_RISK                 # noqa: E402
from mapek.educloud import EduCloudWorld, ProtectedTarget      # noqa: E402
from mapek.guardrails import Guardrails                        # noqa: E402
from mapek.loop import Healer                                  # noqa: E402
from mapek.stages import Planner, Diagnosis                    # noqa: E402
from mapek.world import SimulatedWorld                         # noqa: E402

passed = failed = 0


def check(name, condition, note=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {note}")


LAB = {
    "project_id": "project-A",
    "healer_instance": "healer-ubuntu",
    "lab_instances": ["app-1", "app-2"],
    "template_id": "T", "zone_id": "Z", "offering_id": "O", "network_id": "N",
}


class FakeClient:
    """Records calls instead of making them."""

    def __init__(self, vms):
        self.vms = vms
        self.destroyed = []
        self.deployed = []
        self.rebooted = []

    def instance(self, name):
        return self.vms.get(name)

    def ip_of(self, vm):
        return vm.get("ip")

    def destroy(self, vm_id, expunge=True):
        self.destroyed.append(vm_id)

    def deploy(self, *args):
        self.deployed.append(args[0])

    def reboot(self, vm_id):
        self.rebooted.append(vm_id)


def fake_world(name, vms=None):
    vms = vms or {
        "healer-ubuntu": {"id": "vm-healer", "state": "Running",
                          "ip": "10.1.1.205", "projectid": "project-A"},
        "app-1": {"id": "vm-app1", "state": "Running",
                  "ip": "10.1.1.50", "projectid": "project-A"},
        "stray": {"id": "vm-stray", "state": "Running",
                  "ip": "10.1.1.90", "projectid": "project-B"},
    }
    client = FakeClient(vms)
    world = EduCloudWorld(client, name, LAB)
    return client, world


print("Safety tests\n")

# ---------------------------------------------------------------- catalogue

planner = Planner(CATALOGUE)
try:
    Planner({"restart_service": CATALOGUE["restart_service"]})
    check("planner rejects a catalogue missing its plan actions", False)
except ValueError:
    check("planner rejects a catalogue missing its plan actions", True)

check("every high-risk name is a real action", HIGH_RISK <= set(CATALOGUE))
check("platform repairs are reachable from a plan",
      any("rebuild_instance" in level
          for levels in Planner.PLANS.values() for level in levels))

# --------------------------------------------------------------- guardrails

g = Guardrails(cooldown_ticks=5, max_actions_per_window=99)
g.record(["restart_service"], tick=10)
allowed, reason = g.check(["restart_service"], tick=12)
check("cool-down blocks a repeated action", not allowed and "cool-down" in reason)

g = Guardrails(cooldown_ticks=0, max_actions_per_window=3, window=20)
g.record(["a", "b", "c"], tick=1)
allowed, _ = g.check(["d"], tick=5)
check("rate limit blocks a fourth action in the window", not allowed)

# ------------------------------------------------------- destructive targets

client, world = fake_world("healer-ubuntu")
try:
    world.rebuild_instance()
    check("adapter refuses to rebuild the healer", False,
          f"destroyed={client.destroyed}")
except ProtectedTarget:
    check("adapter refuses to rebuild the healer", not client.destroyed)

client, world = fake_world("healer-ubuntu")
try:
    world.reboot_instance()
    check("adapter refuses to reboot the healer", False)
except ProtectedTarget:
    check("adapter refuses to reboot the healer", not client.rebooted)

client, world = fake_world("stray")
try:
    world.rebuild_instance()
    check("adapter refuses a target outside the allowlist", False)
except ProtectedTarget:
    check("adapter refuses a target outside the allowlist", not client.destroyed)

client, world = fake_world("app-1")
client.vms["app-1"]["projectid"] = "project-B"
try:
    world.rebuild_instance()
    check("adapter refuses an instance from another project", False)
except ProtectedTarget:
    check("adapter refuses an instance from another project", not client.destroyed)

# --------------------------------------------------------- approval gate

world = SimulatedWorld()
world.inject("service_stop")
healer = Healer(world, config="B", approve_high_risk=False)
# make the guest repair fail so the loop escalates to a platform action
world.restart_service = lambda: (False, "simulated repair failure")
healer.run(8)
escalations = [e for e in healer.events if e.kind == "escalated"]
check("high-risk action is not run without approval",
      world.rebuilds == 0 and world.reboots == 0 and len(escalations) > 0)
check("the proposal is recorded for a human to approve",
      any("reboot_instance" in p["actions"] or "rebuild_instance" in p["actions"]
          for p in healer.pending_approval),
      f"pending={healer.pending_approval}")

# ------------------------------------------------------------------- probes

world = SimulatedWorld()
world.inject("unreachable")
observation = world.observe()
check("an unreachable target reports no measurements, not zeros",
      observation["disk_percent"] is None and observation["reachable"] is False)

healer = Healer(world, config="B", approve_high_risk=False)
healer.tick()
check("an unreachable target is diagnosed, not read as healthy",
      any(e.cause == "instance_unreachable" or "approval" in e.detail
          for e in healer.events),
      f"events={[(e.kind, e.cause, e.detail) for e in healer.events]}")

# ------------------------------------------------------- one sample per tick

class CountingWorld(SimulatedWorld):
    def __init__(self):
        super().__init__()
        self.samples = 0

    def observe(self, sample=True):
        if sample:
            self.samples += 1
        return super().observe(sample)


world = CountingWorld()
world.inject("service_stop")
healer = Healer(world, config="B")
healer.run(3)
check("exactly one sampling observation per tick", world.samples == 3,
      f"samples={world.samples}")

# ------------------------------------------------------------ idempotency

world = SimulatedWorld()
world.inject("config_drift")
CATALOGUE["restore_config"](world)
first = world.observe(sample=False)
CATALOGUE["restore_config"](world)
check("restore_config is idempotent", world.observe(sample=False) == first)

# --------------------------------------------------------------- quiet runs

world = SimulatedWorld()
healer = Healer(world, config="C")
healer.run(50)
acted = [e for e in healer.events if e.kind in ("healed", "prevented")]
check("no action during 50 healthy ticks", len(acted) == 0)

# -------------------------------------------------------------- verification

class BrokenRepairWorld(SimulatedWorld):
    def clear_logs(self):
        return True, "reported success but freed nothing"


world = BrokenRepairWorld(disk_start=99.5)
world.inject("service_stop")
healer = Healer(world, config="B", approve_high_risk=False)
healer.run(3)
healed = [e for e in healer.events if e.kind == "healed"]
check("a repair that does not work is never counted as healed", len(healed) == 0)

# ----------------------------------------------------------------- effectors

class ExplodingWorld(SimulatedWorld):
    def restart_service(self):
        raise RuntimeError("ssh died")


world = ExplodingWorld()
world.inject("service_stop")
healer = Healer(world, config="B", approve_high_risk=False)
healer.run(2)
check("an effector that raises becomes a recorded outcome, not a crash",
      any(e.kind == "escalated" for e in healer.events))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
