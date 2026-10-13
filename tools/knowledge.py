"""Look at, and decide on, what the loop has learned. The human side of the loop.

    python3 tools/knowledge.py incidents            every incident, oldest first
    python3 tools/knowledge.py rules                learned prevention rules
    python3 tools/knowledge.py advice [status]      LLM advice (pending, approved, ...)
    python3 tools/knowledge.py approve-advice ID    let the loop use this advice
    python3 tools/knowledge.py reject-advice ID
    python3 tools/knowledge.py approve-rule ID      activate a rule learned with auto_approve off
    python3 tools/knowledge.py events [N]           the last N loop events
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from mapek.knowledge import Knowledge                            # noqa: E402

STATE = os.environ.get("HEALER_STATE", os.path.join(HERE, "state"))


def when(stamp):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(stamp)) if stamp else "-"


def main():
    args = sys.argv[1:] or ["incidents"]
    k = Knowledge(os.path.join(STATE, "knowledge.db"))
    cmd = args[0]
    if cmd == "incidents":
        for r in k.incidents():
            print(f"#{r['id']} {when(r['closed_at'])}  {r['outcome']:<9} {r['cause']}")
            print(f"     symptoms {r['symptoms']}  early signs {r['early_signs']}")
            print(f"     actions  {r['actions']}  source {r['source']}  ticks {r['ticks_to_fix']}")
    elif cmd == "rules":
        for r in k.rules():
            state = "active" if r["approved"] else "awaiting approval"
            print(f"#{r['id']} {when(r['created_at'])}  {state}")
            print(f"     when {r['early_signs']} appear: {r['actions']}  (cause {r['cause']})")
    elif cmd == "advice":
        for r in k.advice(args[1] if len(args) > 1 else None):
            print(f"#{r['id']} {when(r['created_at'])}  {r['status'].upper()}  {r['target']}  "
                  f"risk {r['risk']}  model {r['model']}")
            print(f"     why asked : {r['reason']}")
            print(f"     symptoms  : {r['symptoms']}")
            print(f"     cause     : {r['cause']}")
            print(f"     actions   : {r['actions']}")
            print(f"     reasoning : {r['explanation']}")
            print(f"     check     : {r['human_checks']}")
    elif cmd in ("approve-advice", "reject-advice"):
        ok = k.decide_advice(int(args[1]), cmd == "approve-advice",
                             who=os.environ.get("USER", "human"))
        print("done" if ok else "no pending advice with that id")
    elif cmd == "approve-rule":
        print("done" if k.approve_rule(int(args[1])) else "no rule with that id")
    elif cmd == "events":
        n = int(args[1]) if len(args) > 1 else 20
        try:
            with open(os.path.join(STATE, "events.jsonl")) as fh:
                lines = fh.readlines()[-n:]
        except OSError:
            lines = []
        for line in lines:
            e = json.loads(line)
            print(f"{e['time']} {e['node']:<6} {e['kind'].upper():<10} L{e['level']} "
                  f"{e['cause']} [{e['source']}] {e['detail'][:110]}")
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
