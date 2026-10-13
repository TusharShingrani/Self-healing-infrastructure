"""Manage the EduCloud lab: deploy, check, reset, destroy.

Resets redeploy a fresh instance from the clean template rather than reverting
a snapshot. Not because of the quota: a retained snapshot can be reverted any
number of times. The reason is isolation and reproducibility, so one run cannot
contaminate the next. The retained snapshot stays as a recovery reference.

Run from the healer instance, with credentials in the environment:

    export CS_URL=https://<portal-host>/client/api
    export CS_KEY=...
    export CS_SECRET=...

    python3 tools/lab.py status
    python3 tools/lab.py deploy app-1
    python3 tools/lab.py reset app-1
    python3 tools/lab.py destroy app-1
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapek.cloudstack import CloudStack, CloudStackError        # noqa: E402
from mapek.educloud import EduCloudWorld, ProtectedTarget       # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_lab():
    with open(os.path.join(HERE, "config", "lab.json")) as fh:
        return json.load(fh)


def client(lab):
    return CloudStack(project=lab["project_id"])


def world_for(cs, lab, name, key_path):
    return EduCloudWorld(cs, name, lab, key_path=key_path)


def cmd_status(cs, lab, args):
    vms = cs.instances()
    if not vms:
        print("no instances visible. Is CS_PROJECT or project_id correct?")
        return
    print(f"{'name':<18}{'state':<12}{'ip':<16}{'id'}")
    for vm in sorted(vms, key=lambda v: v["name"]):
        print(f"{vm['name']:<18}{vm['state']:<12}"
              f"{cs.ip_of(vm) or '-':<16}{vm['id']}")


def assert_deploy_allowed(lab, name):
    """Creating an instance is a mutation too, so it gets the same allowlist.

    Without a project id the deploy would land outside the lab project, where
    the ownership check would later refuse to manage or remove it.
    """
    healer = lab.get("healer_instance")
    if healer and name == healer:
        raise ProtectedTarget(f"refusing to deploy over the healer name {healer!r}")
    allowlist = lab.get("lab_instances", [])
    if name not in allowlist:
        raise ProtectedTarget(f"{name!r} is not in lab_instances {sorted(allowlist)}")
    if not lab.get("project_id"):
        raise ProtectedTarget("no project_id configured, refusing to deploy")


def cmd_deploy(cs, lab, args):
    assert_deploy_allowed(lab, args.name)
    if cs.instance(args.name):
        sys.exit(f"{args.name} already exists. Use reset to replace it.")
    print(f"deploying {args.name} from {lab['template_name']} ...")
    started = time.time()
    cs.deploy(args.name, lab["template_id"], lab["zone_id"],
              lab["offering_id"], lab["network_id"], lab.get("keypair"))
    world = world_for(cs, lab, args.name, args.key)
    ready = world.wait_until_ready()
    took = time.time() - started
    print(f"{'ready' if ready else 'deployed but NOT reachable'} after {took:.0f}s")
    if not ready:
        print("check: is the healer on the same network, and is the key correct?")
        sys.exit(1)


def cmd_reset(cs, lab, args):
    """The experiment reset: a fresh instance from the clean template.

    The adapter enforces the allowlist and the healer protection, so this
    command cannot be the only thing standing between a typo and the healer.
    """
    world = world_for(cs, lab, args.name, args.key)
    print(f"resetting {args.name} ...")
    started = time.time()
    ok, detail = world.rebuild_instance()
    print(f"{detail} after {time.time() - started:.0f}s")
    sys.exit(0 if ok else 1)


def cmd_destroy(cs, lab, args):
    """Manual destruction goes through the same checks as an automatic one.

    A name typed by hand is at least as likely to be wrong as one chosen by the
    loop, so the CLI must not have its own weaker path.
    """
    world = world_for(cs, lab, args.name, args.key)
    ok, detail = world.destroy_instance()
    print(detail)
    sys.exit(0 if ok else 1)


def cmd_check(cs, lab, args):
    world = world_for(cs, lab, args.name, args.key)
    obs = world.observe(sample=False)
    for key, value in obs.items():
        print(f"  {key:<18}{value}")
    print(f"\nhealthy: {world.health(obs)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", default=os.environ.get("LAB_SSH_KEY"),
                        help="private key for the lab instances")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")
    for name in ("deploy", "reset", "destroy", "check"):
        p = sub.add_parser(name)
        p.add_argument("name")

    args = parser.parse_args()
    lab = load_lab()
    try:
        cs = client(lab)
    except CloudStackError as error:
        sys.exit(f"CloudStack error: {error}")

    handlers = {"status": cmd_status, "deploy": cmd_deploy, "reset": cmd_reset,
                "destroy": cmd_destroy, "check": cmd_check}
    try:
        handlers[args.command](cs, lab, args)
    except ProtectedTarget as error:
        sys.exit(f"refused: {error}")
    except CloudStackError as error:
        sys.exit(f"CloudStack error: {error}")


if __name__ == "__main__":
    main()
