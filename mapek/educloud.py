"""The real managed element: a lab instance on EduCloud.

Same interface as SimulatedWorld, so the loop, stages, knowledge and guardrails
work against either. Interchangeability is a property of the interface, not a
claim that those files never change.

Safety, enforced here because this is what calls the destructive API:

  - a destructive action may only target a name in the lab allowlist
  - it may never target the healer instance
  - ownership must be positively proven: a configured project id, and an
    instance whose projectid matches it exactly. Missing metadata fails closed.

Probes:

  - a probe that fails returns None, never a plausible number
  - a required probe that could not be read prevents a verified-success result
  - SSH timeouts become a reachability outcome, not an exception
  - an unexplained host key change is reported, never silently accepted
"""

import json
import os
import shlex
import subprocess
import time
import urllib.error
import urllib.request


class ProtectedTarget(RuntimeError):
    """Raised when a destructive action is aimed at something it must not be."""


class HostIdentityChanged(RuntimeError):
    """Raised when a host key changed without an explained instance change."""


# Probes that must be readable before the loop may call the target healthy.
REQUIRED_PROBES = ("service_running", "config_correct", "http_ok")


def lab_state_dir():
    """Where the adapter keeps host identity state. Tests point this elsewhere."""
    return os.environ.get("HEALER_LAB_STATE") or os.path.expanduser(
        "~/.local/state/healer-lab")


def known_hosts_dir():
    """One known_hosts file per lab address. Forgetting one host then deletes
    one small file, instead of rewriting a shared file that other processes are
    using at the same time, which is how unrelated keys used to get lost."""
    return os.environ.get("HEALER_KNOWN_HOSTS_DIR") or os.path.expanduser(
        "~/.ssh/healer-lab-known-hosts")


class HostRegistry:
    """Remembers which instance id was last seen at which address.

    Without this, a fresh process cannot tell an expected key change (a new
    instance at a reused address) from an unexplained one (the same instance
    presenting a different key). The first is routine, the second needs a human
    to verify through the console before anything is trusted.
    """

    def __init__(self, path=None):
        self.path = path or os.path.join(lab_state_dir(), "hosts.json")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        try:
            with open(self.path) as fh:
                self.data = json.load(fh)
        except (OSError, ValueError):
            self.data = {}

    def known_instance(self, address):
        return self.data.get(address, {}).get("instance_id")

    def remember(self, address, instance_id):
        self.data[address] = {"instance_id": instance_id, "seen": time.time()}
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.data, fh, indent=2)
        os.replace(tmp, self.path)


class SSHTarget:
    """Runs commands on a lab instance over SSH, from the healer instance."""

    HOST_KEY_ERRORS = ("REMOTE HOST IDENTIFICATION HAS CHANGED",
                       "Host key verification failed")

    def __init__(self, host, user="ubuntu", key_path=None, known_hosts=None,
                 timeout=20):
        self.host = host
        self.user = user
        self.key_path = key_path
        self.per_host_file = known_hosts is None
        if self.per_host_file:
            os.makedirs(known_hosts_dir(), mode=0o700, exist_ok=True)
            known_hosts = os.path.join(known_hosts_dir(), host)
        self.known_hosts = known_hosts
        self.timeout = timeout
        self.last_error = ""

    def _argv(self, command):
        argv = ["ssh", "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=accept-new",
                "-o", f"UserKnownHostsFile={self.known_hosts}",
                "-o", f"ConnectTimeout={self.timeout}"]
        if self.key_path:
            argv += ["-i", self.key_path, "-o", "IdentitiesOnly=yes"]
        return argv + [f"{self.user}@{self.host}", command]

    def run(self, command):
        """Returns (ok, stdout, stderr). Never raises for a failed connection."""
        try:
            result = subprocess.run(self._argv(command), capture_output=True,
                                    text=True, timeout=self.timeout + 15)
        except subprocess.TimeoutExpired:
            self.last_error = "ssh timed out"
            return False, "", self.last_error
        except OSError as error:
            self.last_error = f"ssh could not run: {error}"
            return False, "", self.last_error
        self.last_error = result.stderr.strip()
        if any(marker in self.last_error for marker in self.HOST_KEY_ERRORS):
            raise HostIdentityChanged(
                f"host key for {self.host} changed: {self.last_error[:160]}")
        return result.returncode == 0, result.stdout.strip(), self.last_error

    def reachable(self):
        ok, _, _ = self.run("true")
        return ok

    def forget_host(self):
        """Remove a stale host record. Only called for an explained change.

        Forgetting an old key is not proof that the new one is authentic. It is
        only valid when the API has shown a different instance id at this
        address, which explains why the key differs.
        """
        if self.per_host_file:
            try:
                os.remove(self.known_hosts)
            except FileNotFoundError:
                pass
            return
        subprocess.run(["ssh-keygen", "-f", self.known_hosts, "-R", self.host],
                       capture_output=True, text=True)


class EduCloudWorld:
    def __init__(self, cloudstack, instance_name, lab, key_path=None,
                 known_hosts=None, registry=None, http_timeout=5, metrics=None):
        self.cs = cloudstack
        # Optional PrometheusSource. When set, the primary Monitor reading
        # comes from Prometheus, and verification after a repair still uses
        # direct probes, so a repair is never judged on a stale scrape.
        self.metrics = metrics
        self.name = instance_name
        self.lab = lab
        self.key_path = key_path
        self.known_hosts = known_hosts
        self.registry = registry if registry is not None else HostRegistry()
        self.http_timeout = http_timeout

        self.service = lab.get("service", "nginx")
        self.log_mount = lab.get("log_mount", "/var/log/nginx")
        self.log_image = lab.get("log_image", "/var/lib/healer/nginx-logs.img")
        self.log_mount_max_mb = int(lab.get("log_mount_max_mb", 1024))
        self.log_mount_fstype = lab.get("log_mount_fstype", "ext4")
        self.config_path = lab.get("config_path", "/etc/nginx/conf.d/healer.conf")
        self.reference_dir = lab.get("reference_dir", "/opt/healer/reference")
        self.health_path = lab.get("health_path", "/healthz")
        self.health_body = lab.get("health_body", "ok")
        self.rotation_policy = lab.get("rotation_policy",
                                       "/etc/logrotate.d/nginx-healer")

        self.tick_count = 0
        self.downtime_ticks = 0
        self.last_action_at = 0.0       # when an effector last changed the instance
        self._last_disk = None
        self._last_seen = None
        self._vm = None
        self._ssh = None
        self._identity_problem = ""

    # ------------------------------------------------------------ protection

    def _assert_destructive_allowed(self):
        """Fails closed. Every condition must be positively satisfied."""
        healer = self.lab.get("healer_instance")
        if healer and self.name == healer:
            raise ProtectedTarget(
                f"refusing a destructive action on the healer instance {healer!r}")

        allowlist = set(self.lab.get("lab_instances", []))
        if self.name not in allowlist:
            raise ProtectedTarget(
                f"{self.name!r} is not in lab_instances {sorted(allowlist)}")

        expected = self.lab.get("project_id")
        if not expected:
            raise ProtectedTarget(
                "no project_id configured, so ownership cannot be proven")

        vm = self._refresh()
        if not vm:
            raise ProtectedTarget(f"{self.name!r} not found, ownership unproven")

        owner = vm.get("projectid")
        if not owner:
            raise ProtectedTarget(
                f"{self.name!r} has no projectid, so ownership cannot be proven")
        if owner != expected:
            raise ProtectedTarget(
                f"{self.name!r} belongs to project {owner}, not {expected}")
        return vm

    # -------------------------------------------------------------- plumbing

    def _refresh(self):
        self._vm = self.cs.instance(self.name)
        self._identity_problem = ""
        if not self._vm:
            return None

        instance_id = self._vm.get("id")
        address = self.cs.ip_of(self._vm)
        if not address:
            return self._vm

        if self._ssh is None or self._ssh.host != address:
            self._ssh = SSHTarget(address, key_path=self.key_path,
                                  known_hosts=self.known_hosts)

        known = self.registry.known_instance(address)
        if known and known != instance_id:
            # a different instance now answers at this address, so a different
            # host key is expected and the stale record may be removed
            self._ssh.forget_host()
        self.registry.remember(address, instance_id)
        return self._vm

    def _probe(self, command):
        """Run a probe, turning an unexplained identity change into a state."""
        try:
            return self._ssh.run(command)
        except HostIdentityChanged as error:
            self._identity_problem = str(error)
            return False, "", str(error)

    # ---------------------------------------------------------------- probes

    def observe(self, sample=True):
        obs = {
            "tick": self.tick_count, "instance_state": None, "reachable": False,
            "service_running": None, "disk_percent": None, "disk_growth": None,
            "config_correct": None, "http_ok": None, "probe_error": "",
        }
        vm = self._refresh()
        if not vm:
            obs["instance_state"] = "Absent"
            obs["probe_error"] = "instance not found in project"
            return obs

        obs["instance_state"] = vm.get("state")
        if vm.get("state") != "Running" or not self._ssh:
            obs["probe_error"] = f"instance state {vm.get('state')}"
            return obs

        ok, _, err = self._probe("true")
        if self._identity_problem:
            obs["probe_error"] = (
                f"{self._identity_problem}. Verify the new key through the "
                f"console before trusting this host.")
            return obs
        if not ok:
            obs["probe_error"] = err or "ssh unreachable"
            return obs
        obs["reachable"] = True

        errors = []
        from_metrics = {}
        if self.metrics is not None and sample:
            from_metrics, stale = self.metrics.observe(
                self.name, newer_than=self.last_action_at)
            obs.update(from_metrics)
            obs["monitor_source"] = ("prometheus" if len(from_metrics) == 5
                                     else "prometheus+direct")
            if stale:
                obs["stale_metrics"] = stale
        else:
            obs["monitor_source"] = "direct"

        if "service_running" not in from_metrics:
            self._probe_service(obs, errors)

        if "disk_percent" in from_metrics:
            if sample:
                self._last_disk, self._last_seen = obs["disk_percent"], time.time()
        else:
            self._probe_disk(obs, errors, sample)

        if "config_correct" not in from_metrics:
            self._probe_config(obs, errors)

        if "http_ok" not in from_metrics:
            obs["http_ok"] = self._http_ok()
            if obs["http_ok"] is None:
                errors.append("availability probe could not be run")

        obs["probe_error"] = "; ".join(errors)
        return obs

    def _probe_service(self, obs, errors):
        ok, out, err = self._probe(f"systemctl is-active {shlex.quote(self.service)}")
        state = out.strip()
        if state in ("active", "activating"):
            obs["service_running"] = True
        elif state in ("inactive", "failed", "deactivating"):
            obs["service_running"] = False
        else:
            errors.append(f"service probe unreadable: {err or state or 'no output'}")

    def _probe_disk(self, obs, errors, sample):
        ok, out, err = self._probe(
            f"df --output=pcent {shlex.quote(self.log_mount)} | tail -1 | tr -dc '0-9'")
        if ok and out.isdigit():
            disk = float(out)
            obs["disk_percent"] = disk
            now = time.time()
            if self._last_disk is not None and self._last_seen and now > self._last_seen:
                obs["disk_growth"] = round(
                    (disk - self._last_disk) / (now - self._last_seen) * 60, 2)
            if sample:
                self._last_disk, self._last_seen = disk, now
        else:
            errors.append(f"disk probe failed: {err or 'no output'}")

    def _probe_config(self, obs, errors):
        ok, _, err = self._probe(
            f"sudo nginx -t && sudo diff -q {shlex.quote(self.config_path)} "
            f"{shlex.quote(self.reference_dir)}/healer.conf")
        if err and ("command not found" in err or "No such file" in err):
            errors.append(f"config probe failed: {err}")
        else:
            obs["config_correct"] = ok

    def _http_ok(self):
        """Service-level availability, independent of what systemd says.

        Probes the specific health endpoint and checks its body. A default root
        page can return 200 while the endpoint under test is broken, so the
        root is not a valid availability signal.
        """
        if not self._ssh:
            return None
        url = f"http://{self._ssh.host}{self.health_path}"
        try:
            with urllib.request.urlopen(url, timeout=self.http_timeout) as response:
                if response.status != 200:
                    return False
                body = response.read(256).decode("utf-8", "replace")
                # exact match after normalising whitespace. A substring test
                # would accept "broken" as healthy when the expected body is
                # "ok", which is the opposite of what the probe is for.
                return body.strip() == self.health_body.strip()
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
            return False

    def health(self, observation):
        """Healthy means every required probe was readable and satisfied.

        Disk usage is not a service requirement, so it is not required here.
        A required probe that could not be read is not health, it is unknown,
        and unknown must never verify a repair as successful.
        """
        if not observation.get("reachable"):
            return False
        if observation.get("probe_error"):
            return False
        for probe in REQUIRED_PROBES:
            if observation.get(probe) is not True:
                return False
        return True

    def note_health(self, healthy):
        if not healthy:
            self.downtime_ticks += 1

    # ------------------------------------------------------------ effectors

    def diagnostic_evidence(self):
        """Read-only evidence from the exact managed component, not environment dumps."""
        evidence = {'target': self.name, 'instance_id': (self._vm or {}).get('id'),
                    'address': self._ssh.host if self._ssh else None,
                    'component': self.service, 'config_path': self.config_path,
                    'log_mount': self.log_mount, 'rotation_policy': self.rotation_policy}
        commands = {
            'service': f'systemctl show {shlex.quote(self.service)} -p ActiveState -p SubState -p Result -p ExecMainStatus',
            'config_check': 'sudo nginx -t 2>&1',
            'mount': f'findmnt -no TARGET,SOURCE,FSTYPE {shlex.quote(self.log_mount)}',
            'space': f'df -h {shlex.quote(self.log_mount)}',
            'rotation': f'test -f {shlex.quote(self.rotation_policy)} && echo present',
            'config_identity': f'sudo sha256sum {shlex.quote(self.config_path)} {shlex.quote(self.reference_dir)}/healer.conf',
        }
        if self._ssh:
            for name, command in commands.items():
                ok, out, err = self._probe(command)
                evidence[name] = {'command_success': ok, 'stdout': out[:3000], 'stderr': err[:1000]}
        return evidence

    def rotation_verified(self):
        if not self._ssh:
            return False
        command = (f'sudo cmp -s {shlex.quote(self.rotation_policy)} '
                   f'{shlex.quote(self.reference_dir)}/nginx-healer.logrotate && '
                   'test "$(systemctl is-active healer-logflood.timer)" = inactive && '
                   'test "$(systemctl is-active healer-logrotate.timer)" = active')
        ok, _, _ = self._probe(command)
        return ok

    def configuration_verified(self):
        if not self._ssh:
            return False
        ok, _, _ = self._probe('sudo nginx -t')
        return ok

    def repair_identity(self):
        if not self._ssh:
            return {'references': None, 'live_config': None}
        ok, out, _ = self._probe(f'sudo sha256sum {shlex.quote(self.config_path)} '
                                f'{shlex.quote(self.reference_dir)}/healer.conf '
                                f'{shlex.quote(self.reference_dir)}/nginx-healer.logrotate')
        hashes = [line.split()[0] for line in out.splitlines() if line.split()]
        if not ok or len(hashes) != 3 or any(len(h) != 64 for h in hashes):
            return {'references': None, 'live_config': None}
        return {'references': hashes[1:], 'live_config': hashes[0]}

    def _guest(self, command, success):
        if not self._ssh:
            return False, "no ssh target"
        self.last_action_at = time.time()
        ok, _, err = self._probe(command)
        return ok, (success if ok else (err or "command failed"))

    def restart_service(self):
        return self._guest(f"sudo systemctl restart {shlex.quote(self.service)}",
                           f"{self.service} restarted")

    def clear_logs(self):
        return self._guest(
            f"sudo find {shlex.quote(self.log_mount)} -type f "
            f"\\( -name '*.gz' -o -name '*.[0-9]' -o -name '*.old' \\) -delete; "
            f"sudo find {shlex.quote(self.log_mount)} -type f -size +50M "
            f"-exec truncate -s 0 {{}} \\;",
            "log filesystem reclaimed")

    def fix_log_rotation(self):
        """Repairs the cause: restores the policy and stops the producer.

        The flood generator models a broken-rotation condition, not normal
        traffic, and it refuses to run once the policy file exists. Stopping the
        timer as well makes the repair immediate rather than waiting for the
        generator to notice.
        """
        return self._guest(
            f"sudo cp {shlex.quote(self.reference_dir)}/nginx-healer.logrotate "
            f"{shlex.quote(self.rotation_policy)} && "
            f"sudo systemctl stop healer-logflood.timer healer-logflood.service "
            f"2>/dev/null; "
            f"sudo logrotate -f {shlex.quote(self.rotation_policy)}",
            "log rotation restored, producer stopped, rotation run once")

    def restore_config(self):
        return self._guest(
            f"sudo cp {shlex.quote(self.reference_dir)}/healer.conf "
            f"{shlex.quote(self.config_path)} && sudo nginx -t && "
            # reload-or-restart: a plain reload fails when an invalid config
            # has already stopped nginx, and the repair would then escalate
            f"sudo systemctl reload-or-restart {shlex.quote(self.service)}",
            "configuration restored from reference")

    # -------------------------------------------------- platform level repairs

    def reboot_instance(self):
        vm = self._assert_destructive_allowed()
        self.last_action_at = time.time()
        self.cs.reboot(vm["id"])
        return self.wait_until_ready(), "instance rebooted"

    def rebuild_instance(self):
        """Destroy and redeploy from the clean template. High risk and slow."""
        vm = self._assert_destructive_allowed()
        self.last_action_at = time.time()
        self.cs.destroy(vm["id"], expunge=True)
        self.cs.deploy(self.name, self.lab["template_id"], self.lab["zone_id"],
                       self.lab["offering_id"], self.lab["network_id"],
                       self.lab.get("keypair"),
                       ipaddress=self.lab.get("addresses", {}).get(self.name))
        self._vm = None
        ready = self.wait_until_ready()
        return ready, ("rebuilt from template" if ready
                       else "rebuilt but not reachable")

    def destroy_instance(self):
        """Used by the CLI, so manual destruction passes the same checks."""
        vm = self._assert_destructive_allowed()
        self.cs.destroy(vm["id"], expunge=True)
        self._vm = self._ssh = None
        return True, f"{self.name} destroyed"

    def wait_until_ready(self, limit=600, poll=10):
        deadline = time.time() + limit
        while time.time() < deadline:
            observation = self.observe(sample=False)
            if observation.get("reachable"):
                return True
            if self._identity_problem:
                return False      # never wait out an unexplained key change
            time.sleep(poll)
        return False

    # ------------------------------------------------------------------ time

    def step(self):
        self.tick_count += 1

    # ------------------------------------------------------- fault injection

    def assert_bounded_log_mount(self):
        """Refuse to flood anything but the expected dedicated, bounded volume.

        A pathname check alone is not enough: a bind mount backed by the root
        filesystem has the right target, and a huge dedicated volume is still
        the wrong thing to fill. Four conditions must all hold.
        """
        if not self._ssh:
            raise RuntimeError("no ssh target")

        mount = shlex.quote(self.log_mount)
        ok, out, err = self._probe(
            f"M={mount}; S=$(findmnt -no SOURCE --target \"$M\"); "
            f"findmnt -bno TARGET,SOURCE,FSTYPE,SIZE --target \"$M\"; echo ---; "
            f"findmnt -bno SOURCE --target /; echo ---; "
            f"stat -c %d \"$M\" /; echo ---; "
            f"losetup -nO BACK-FILE \"$S\" 2>/dev/null || true")
        if not ok or out.count("---") != 3:
            raise RuntimeError(f"cannot confirm the log mount: {err or 'no output'}")

        mount_line, root_source, devices, backing = [p.strip()
                                                     for p in out.split("---")]
        fields = mount_line.split()
        if len(fields) < 4:
            raise RuntimeError(f"unreadable mount description: {mount_line!r}")
        target, source, fstype, size = fields[0], fields[1], fields[2], fields[3]

        if target != self.log_mount:
            raise RuntimeError(
                f"{self.log_mount} is not its own mount point (it resolves to "
                f"{target}). The installer must create a bounded filesystem "
                f"there before any disk fault is injected.")
        if target == "/":
            raise RuntimeError("refusing to flood the root filesystem")

        # a bind mount of the root filesystem shares root's device number
        device_ids = devices.split()
        if len(device_ids) == 2 and device_ids[0] == device_ids[1]:
            raise RuntimeError(
                f"{self.log_mount} shares a device with the root filesystem, "
                f"so it is a bind mount rather than a bounded volume")
        if source == root_source:
            raise RuntimeError(
                f"{self.log_mount} is backed by the root source {source}")
        if self.log_mount_fstype and fstype != self.log_mount_fstype:
            raise RuntimeError(
                f"{self.log_mount} is {fstype}, expected {self.log_mount_fstype}")

        try:
            size_mb = int(size) // (1024 * 1024)
        except ValueError:
            raise RuntimeError(f"unreadable mount size: {size!r}") from None
        if size_mb <= 0 or size_mb > self.log_mount_max_mb:
            raise RuntimeError(
                f"{self.log_mount} is {size_mb} MiB, outside the permitted "
                f"bound of 1 to {self.log_mount_max_mb} MiB")

        if self.log_image:
            if not backing:
                raise RuntimeError(
                    f"{self.log_mount} source {source} is not loop backed, so "
                    f"it is not the expected bounded image")
            if backing != self.log_image:
                raise RuntimeError(
                    f"{self.log_mount} is backed by {backing}, expected "
                    f"{self.log_image}")
        return f"{target} {source} {fstype} {size_mb}MiB"

    def inject(self, fault):
        """Experiment only. Never part of the healer. Returns (ok, detail)."""
        if not self._ssh:
            raise RuntimeError("no ssh target")
        if fault == "service_stop":
            ok, _, err = self._probe(
                f"sudo systemctl stop {shlex.quote(self.service)}")
            return ok, err or "service stopped"
        if fault == "disk_leak":
            mount = self.assert_bounded_log_mount()
            ok1, _, e1 = self._probe(
                f"sudo rm -f {shlex.quote(self.rotation_policy)}")
            ok2, _, e2 = self._probe("sudo systemctl start healer-logflood.timer")
            if not (ok1 and ok2):
                return False, f"could not start the fault: {e1} {e2}".strip()
            filled, detail = self._confirm_filling()
            return filled, (f"{detail} on {mount}" if filled
                            else f"fault did not take hold: {detail}")
        if fault == "config_drift":
            ok, _, err = self._probe(
                f"sudo bash -c \"echo 'worker_processes nonsense;' >> "
                f"{shlex.quote(self.config_path)}\"")
            return ok, err or "configuration altered"
        raise ValueError(f"unknown fault: {fault}")

    def _confirm_filling(self, limit=90, poll=10, minimum_growth=2.0):
        """A started timer proves scheduling, not that the fault took hold.

        Watches the bounded filesystem until it has measurably filled, so a
        silent failure cannot be recorded as a successful injection.
        """
        start = None
        deadline = time.time() + limit
        while time.time() < deadline:
            ok, out, err = self._probe(
                f"df --output=pcent {shlex.quote(self.log_mount)} "
                f"| tail -1 | tr -dc '0-9'")
            if not ok or not out.isdigit():
                return False, f"cannot measure the log filesystem: {err}"
            used = float(out)
            if start is None:
                start = used
            if used >= 99 or used - start >= minimum_growth:
                return True, f"log filesystem at {used:.0f}% and rising"
            time.sleep(poll)
        return False, (f"log filesystem did not grow beyond {start:.0f}% within "
                       f"{limit}s. Check healer-logflood for errors.")

    def maintenance_restart(self):
        """A deliberate restart, the lab's defined maintenance operation.

        A restart, not a reload. nginx validates a new configuration and rolls
        back to the running one if it cannot apply it, so a reload is not a
        reliable way to surface a latent problem. The lab host instead declares
        an explicit startup storage requirement through an ExecStartPre
        preflight, so a restart fails deterministically when the bounded log
        filesystem is too full. That requirement is a lab protocol, not stock
        nginx behaviour, and the report must say so.
        """
        ok, _, err = self._probe(
            f"sudo systemctl restart {shlex.quote(self.service)}")
        return ok, err or "restarted"

    def stop_fault(self):
        if self._ssh:
            self._probe("sudo systemctl stop healer-logflood.timer "
                        "healer-logflood.service")


def load_lab(path=None):
    path = path or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "lab.json")
    with open(path) as fh:
        return json.load(fh)
