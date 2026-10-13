"""Tests against the real adapter, EduCloudWorld, not the simulation.

These cover the cases where the adapter and the CLI can differ from the
simulated world: ownership proof, destructive routing, health with unreadable
probes, approval accounting, host identity, and fault-injection preconditions.

No EduCloud calls are made. A fake client records what would have happened.

Run:  python3 tools/test_adapter.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapek.educloud import (EduCloudWorld, HostRegistry, ProtectedTarget,  # noqa: E402
                            REQUIRED_PROBES)
from mapek.loop import Healer                                              # noqa: E402
from mapek.world import SimulatedWorld                                     # noqa: E402

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
    def __init__(self, vms):
        self.vms = vms
        self.destroyed, self.deployed, self.rebooted = [], [], []

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


def build(name, vms=None, registry_path=None):
    vms = vms if vms is not None else {
        "healer-ubuntu": {"id": "vm-healer", "state": "Running",
                          "ip": "10.1.1.205", "projectid": "project-A"},
        "app-1": {"id": "vm-app1", "state": "Running",
                  "ip": "10.1.1.50", "projectid": "project-A"},
        "no-owner": {"id": "vm-noowner", "state": "Running", "ip": "10.1.1.60"},
        "other-project": {"id": "vm-other", "state": "Running",
                          "ip": "10.1.1.70", "projectid": "project-B"},
    }
    client = FakeClient(vms)
    registry = HostRegistry(registry_path or os.path.join(
        tempfile.mkdtemp(), "hosts.json"))
    return client, EduCloudWorld(client, name, LAB, registry=registry)


print("Adapter tests\n")

# ------------------------------------------------------- ownership proof

for target, label in [("healer-ubuntu", "the healer"),
                      ("other-project", "another project's instance"),
                      ("no-owner", "an instance with no project metadata")]:
    lab = dict(LAB)
    if target != "healer-ubuntu":
        lab = dict(LAB, lab_instances=LAB["lab_instances"] + [target])
    client, world = build(target)
    world.lab = lab
    try:
        world.rebuild_instance()
        check(f"rebuild refuses {label}", False, f"destroyed={client.destroyed}")
    except ProtectedTarget:
        check(f"rebuild refuses {label}", not client.destroyed)

client, world = build("app-1")
world.lab = dict(LAB, project_id=None)
try:
    world.rebuild_instance()
    check("rebuild refuses when no project id is configured", False)
except ProtectedTarget:
    check("rebuild refuses when no project id is configured", not client.destroyed)

# -------------------------------------------------- destructive routing

client, world = build("no-owner")
world.lab = dict(LAB, lab_instances=["app-1", "no-owner"])
try:
    world.destroy_instance()
    check("destroy_instance applies the same ownership check", False,
          f"destroyed={client.destroyed}")
except ProtectedTarget:
    check("destroy_instance applies the same ownership check",
          not client.destroyed)

client, world = build("healer-ubuntu")
try:
    world.destroy_instance()
    check("destroy_instance refuses the healer", False)
except ProtectedTarget:
    check("destroy_instance refuses the healer", not client.destroyed)

# ----------------------------------------------------------------- health

_, world = build("app-1")

healthy = {"reachable": True, "service_running": True, "config_correct": True,
           "http_ok": True, "disk_percent": 40.0, "probe_error": ""}
check("a fully readable, satisfied observation is healthy", world.health(healthy))

unknown_config = dict(healthy, config_correct=None,
                      probe_error="config probe failed")
check("an unreadable required probe is not health",
      not world.health(unknown_config))

silent_unknown = dict(healthy, config_correct=None, probe_error="")
check("a required probe of None is not health even without an error message",
      not world.health(silent_unknown))

no_http = dict(healthy, http_ok=False)
check("a running unit that does not serve is not health", not world.health(no_http))

full_disk = dict(healthy, disk_percent=99.0)
check("disk usage alone does not make a serving instance unhealthy",
      world.health(full_disk))

check("http availability is a required probe", "http_ok" in REQUIRED_PROBES)

# ------------------------------------------------- approval accounting

class FailingWorld(SimulatedWorld):
    """Guest repair always fails, so the loop wants to escalate."""

    def __init__(self):
        super().__init__()
        self.name = "app-1"

    def restart_service(self):
        return False, "simulated guest repair failure"


world = FailingWorld()
world.inject("service_stop")
healer = Healer(world, config="B", approve_high_risk=False)
healer.run(10)
check("unapproved ticks do not consume escalation levels",
      world.reboots == 0 and world.rebuilds == 0 and
      len(healer.pending_approval) == 1,
      f"pending={len(healer.pending_approval)}")
check("the proposal names its target and action",
      healer.pending_approval[0]["target"] == "app-1" and
      "reboot_instance" in healer.pending_approval[0]["actions"])

# once approved, the still-pending level must actually run
healer.approve_high_risk = True
healer.run(6)
check("after approval the pending level executes", world.reboots >= 1,
      f"reboots={world.reboots}")

# ----------------------------------------------------------- host identity

tmp = os.path.join(tempfile.mkdtemp(), "hosts.json")
registry = HostRegistry(tmp)
registry.remember("10.1.1.50", "vm-app1")
reloaded = HostRegistry(tmp)
check("the instance seen at an address survives a fresh process",
      reloaded.known_instance("10.1.1.50") == "vm-app1")

client, world = build("app-1", registry_path=tmp)
forgotten = []
world._refresh()
world._ssh.forget_host = lambda: forgotten.append(world._ssh.host)
world._refresh()
check("a known instance at a known address does not forget its host key",
      forgotten == [], f"forgotten={forgotten}")

client.vms["app-1"]["id"] = "vm-app1-NEW"
world._refresh()
check("a different instance at the same address forgets the stale record",
      forgotten == ["10.1.1.50"], f"forgotten={forgotten}")

# an unexplained key change must surface, not be waited out
class KeyChangedWorld(EduCloudWorld):
    def _probe(self, command):
        self._identity_problem = "host key for 10.1.1.50 changed"
        return False, "", self._identity_problem


client, _ = build("app-1")
world = KeyChangedWorld(client, "app-1", LAB,
                        registry=HostRegistry(os.path.join(tempfile.mkdtemp(), "h.json")))
observation = world.observe()
check("an unexplained host key change is reported, not accepted",
      not observation["reachable"] and "console" in observation["probe_error"])
check("readiness does not wait out an unexplained key change",
      world.wait_until_ready(limit=30, poll=1) is False)

# ------------------------------------------------ health endpoint probing
#
# These exercise the production _http_ok by patching urlopen, rather than
# overriding the method, so the real status handling and body comparison are
# what is under test.

import io                                                        # noqa: E402
import urllib.error                                              # noqa: E402
import urllib.request                                            # noqa: E402


class FakeResponse(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body.encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def with_http(responses, failure=None):
    """Patch urlopen to serve a map of url -> (body, status)."""
    requested = []

    def fake_urlopen(url, timeout=None):
        requested.append(url)
        if failure:
            raise failure
        if url not in responses:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        body, status = responses[url]
        return FakeResponse(body, status)

    return fake_urlopen, requested


def http_case(name, responses, expected, failure=None):
    _, world = build("app-1")
    world._refresh()
    fake, requested = with_http(responses, failure)
    original = urllib.request.urlopen
    urllib.request.urlopen = fake
    try:
        result = world._http_ok()
    finally:
        urllib.request.urlopen = original
    check(name, result is expected, f"got {result}, requested {requested}")
    return requested


root_only = {"http://10.1.1.50/": ("welcome to nginx", 200)}
requested = http_case("a 200 at the root is not availability", root_only, False)
check("the probe asks for the configured health endpoint",
      requested == ["http://10.1.1.50/healthz"], str(requested))

http_case("the health endpoint with the exact expected body is availability",
          {"http://10.1.1.50/healthz": ("ok\n", 200)}, True)

http_case("a body merely containing the expected token is not availability",
          {"http://10.1.1.50/healthz": ("broken", 200)}, False)

http_case("a longer body containing the token is not availability",
          {"http://10.1.1.50/healthz": ("not ok, degraded", 200)}, False)

http_case("a non-200 status is not availability",
          {"http://10.1.1.50/healthz": ("ok", 503)}, False)

http_case("a transport failure is not availability", {}, False,
          failure=urllib.error.URLError("connection refused"))

http_case("a timeout is not availability", {}, False,
          failure=OSError("timed out"))

# --------------------------------------------------- fault preconditions

MB = 1024 * 1024


def mount_output(target="/var/log/nginx", source="/dev/loop0", fstype="ext4",
                 size_mb=512, root_source="/dev/vda1", same_device=False,
                 backing="/var/lib/healer/nginx-logs.img"):
    """Build the four-part reply the adapter asks the host for."""
    devices = "2049 2049" if same_device else "2305 2049"
    return (f"{target} {source} {fstype} {size_mb * MB}\n---\n"
            f"{root_source}\n---\n{devices}\n---\n{backing}")


class MountWorld(EduCloudWorld):
    def __init__(self, client, output, ok=True):
        super().__init__(client, "app-1", LAB,
                         registry=HostRegistry(os.path.join(tempfile.mkdtemp(),
                                                            "h.json")))
        self._output, self._ok = output, ok
        self.filled = False
        self._refresh()

    def _probe(self, command):
        if "findmnt" in command:
            return self._ok, self._output, "" if self._ok else "findmnt failed"
        if command.startswith("df"):
            return True, "99" if self.filled else "41", ""
        return True, "", ""


client, _ = build("app-1")

cases = [
    ("a log directory that is not its own mount",
     mount_output(target="/"), "its own mount point"),
    ("a bind mount backed by the root filesystem",
     mount_output(same_device=True), "bind mount"),
    ("a mount whose source is the root source",
     mount_output(source="/dev/vda1"), "root source"),
    ("a volume far larger than the configured bound",
     mount_output(size_mb=200 * 1024), "permitted bound"),
    ("the wrong filesystem type",
     mount_output(fstype="tmpfs"), "expected ext4"),
    ("a volume backed by an unexpected image",
     mount_output(backing="/var/lib/healer/other.img"), "expected"),
    ("a volume that is not loop backed",
     mount_output(backing=""), "not loop backed"),
]
for label, output, expected in cases:
    world = MountWorld(client, output)
    try:
        world.inject("disk_leak")
        check(f"disk fault refuses {label}", False)
    except RuntimeError as error:
        check(f"disk fault refuses {label}", expected in str(error), str(error))

world = MountWorld(client, "", ok=False)
try:
    world.inject("disk_leak")
    check("disk fault refuses when the mount cannot be confirmed", False)
except RuntimeError:
    check("disk fault refuses when the mount cannot be confirmed", True)

world = MountWorld(client, mount_output())
world.filled = True
ok, detail = world.inject("disk_leak")
check("disk fault proceeds on a bounded dedicated volume", ok, detail)

world = MountWorld(client, mount_output())
world.filled = False      # the timer started but nothing actually filled
ok, detail = world.inject("disk_leak")
check("a started timer alone is not a successful injection",
      not ok and "did not grow" in detail, detail)

print("\nCLI deploy")

import importlib.util                                                     # noqa: E402
import types                                                              # noqa: E402

spec = importlib.util.spec_from_file_location(
    "lab_cli", os.path.join(os.path.dirname(os.path.abspath(__file__)), "lab.py"))
lab_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab_cli)


class DeployClient:
    def __init__(self):
        self.deployed = []

    def instance(self, name):
        return None

    def deploy(self, name, *args):
        self.deployed.append(name)


for label, name, lab in [
        ("deploy refuses the healer's name", "healer-ubuntu", LAB),
        ("deploy refuses a name outside lab_instances", "app-3", LAB),
        ("deploy refuses when no project id is configured", "app-1",
         dict(LAB, project_id=None))]:
    client = DeployClient()
    try:
        lab_cli.cmd_deploy(client, dict(lab, template_name="T"),
                           types.SimpleNamespace(name=name, key=None))
        check(label, False, "no refusal")
    except ProtectedTarget:
        check(label, not client.deployed)

try:
    lab_cli.assert_deploy_allowed(LAB, "app-1")
    check("deploy allows a listed lab instance", True)
except ProtectedTarget as error:
    check("deploy allows a listed lab instance", False, str(error))

print("\nAPI client configuration")

from mapek.cloudstack import CloudStack, CloudStackError                  # noqa: E402

saved = {k: os.environ.pop(k, None) for k in ("CS_URL", "CS_KEY", "CS_SECRET")}
try:
    os.environ["CS_KEY"] = "a-key-value"
    try:
        CloudStack(project="project-A")
        check("missing credentials are refused with a clear error", False)
    except CloudStackError as error:
        message = str(error)
        check("missing credentials are refused with a clear error",
              "CS_URL" in message and "CS_SECRET" in message, message)
        check("the error names the missing variables, not the set ones",
              "CS_KEY" not in message and "a-key-value" not in message, message)
    except KeyError as error:
        check("missing credentials are refused with a clear error", False,
              f"raw KeyError {error}")
finally:
    for k, v in saved.items():
        os.environ.pop(k, None)
        if v is not None:
            os.environ[k] = v

try:
    CloudStack(url="CS_URL=https://portal.example/client/api", key="K",
               secret="S", project="project-A")
    check("a URL pasted with its variable name is refused", False)
except CloudStackError as error:
    check("a URL pasted with its variable name is refused",
          "pasted with its name" in str(error) and "portal.example" not in str(error),
          str(error))

try:
    CloudStack(url="http://portal.example/client/api", key="K", secret="S",
               project="project-A")
    check("a plain http API URL is refused, the key would travel unencrypted", False)
except CloudStackError:
    check("a plain http API URL is refused, the key would travel unencrypted", True)

# port 9 on loopback: nothing listens, so the connection is refused locally
cs = CloudStack(url="https://127.0.0.1:9/client/api", key="K", secret="S",
                project="project-A", timeout=2)
try:
    cs.instances()
    check("an unreachable API is an error, not an empty instance list", False)
except CloudStackError as error:
    check("an unreachable API is an error, not an empty instance list",
          "could not reach" in str(error), str(error))
    check("the network error does not leak the signed request",
          "apikey" not in str(error) and "signature" not in str(error), str(error))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
