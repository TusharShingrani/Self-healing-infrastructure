"""The action catalogue: the only things the loop is allowed to do.

Every action is a named function with a fixed signature. The planner may only
return names from this dictionary, so the set of possible effects is finite,
reviewable and testable.

Each action must be:
  idempotent   running it twice causes no extra harm
  bounded      its effect is predictable and limited to one concern
  verifiable   the loop can check afterwards whether it worked

HIGH_RISK names must exist in the catalogue, and the loop refuses to run them
without approval. The test suite checks both of those statements.
"""


def restart_service(world):
    return world.restart_service()


def clear_logs(world):
    return world.clear_logs()


def fix_log_rotation(world):
    return world.fix_log_rotation()


def restore_config(world):
    return world.restore_config()


def reboot_instance(world):
    return world.reboot_instance()


def rebuild_instance(world):
    return world.rebuild_instance()


CATALOGUE = {
    "restart_service": restart_service,
    "clear_logs": clear_logs,
    "fix_log_rotation": fix_log_rotation,
    "restore_config": restore_config,
    "reboot_instance": reboot_instance,
    "rebuild_instance": rebuild_instance,
}

# Actions that destroy state or interrupt a whole machine. The loop will not
# run these on its own: it records the proposal and escalates for approval.
HIGH_RISK = {"reboot_instance", "rebuild_instance"}

assert HIGH_RISK <= set(CATALOGUE), "every high-risk name must be a real action"
