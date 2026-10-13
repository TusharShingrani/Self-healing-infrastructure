"""Live demo: the same failure twice. The second time it never happens.

Run:  python3 tools/demo.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapek.world import SimulatedWorld
from mapek.loop import Healer


def banner(text):
    print("\n" + "=" * 68)
    print(text)
    print("=" * 68)


banner("CONFIG C: healing with knowledge. Disk leak injected twice.")

world = SimulatedWorld()
healer = Healer(world, config="C", verbose=True)

def occurrence(label):
    """Inject the leak, let it run, then do the deliberate restart.

    A full log filesystem does not stop a running service on its own. The lab
    host declares a startup storage requirement, so the failure appears at the
    next restart.
    """
    print(f"\n-- {label} --")
    before = world.downtime_ticks
    world.inject("disk_leak")
    healer.run(20)
    print("   deliberate restart ...")
    world.maintenance_restart()
    healer.run(20)
    print(f"   downtime: {world.downtime_ticks - before} ticks")


occurrence("first occurrence: nothing is known yet")
occurrence("second occurrence: the same leak again")

banner("WHAT THE LOOP LEARNED")
for row in healer.knowledge.incidents():
    print(f"  cause={row['cause']}")
    print(f"    symptoms at failure : {row['symptoms']}")
    print(f"    early signs recorded: {row['early_signs']}")
    print(f"    actions             : {row['actions']}  -> {row['outcome']}")
