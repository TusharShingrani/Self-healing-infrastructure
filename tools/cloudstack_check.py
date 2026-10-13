"""Verify what the EduCloud (CloudStack) API account can actually do.

Run this before designing any repair action that touches the platform. It
answers one question: which API commands is this account allowed to call?

Setup (PowerShell):
    $env:CS_URL    = "https://<portal-host>/client/api"
    $env:CS_KEY    = "<api key>"
    $env:CS_SECRET = "<secret key>"
    python tools/cloudstack_check.py

The secret is only ever used to sign requests locally. Never commit it, and
never paste it into a chat or a report.
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import urllib.parse
import urllib.request

# Commands the healer might want. Each one maps to a repair action, so this
# list is really "which repairs are possible on this platform".
WANTED = {
    "listVirtualMachines":    "read instance state (Monitor)",
    "listNetworks":           "read network state (Monitor)",
    "listVolumes":            "read disk state (Monitor)",
    "rebootVirtualMachine":   "reboot action (Execute)",
    "startVirtualMachine":    "start action (Execute)",
    "stopVirtualMachine":     "stop action (Execute)",
    "deployVirtualMachine":   "rebuild from template (Execute)",
    "destroyVirtualMachine":  "destroy a broken instance (Execute, high risk)",
    "createTemplate":         "make the clean template for experiment resets",
    "listTemplates":          "find the clean template",
    "createSnapshot":         "snapshot a volume",
    "revertSnapshot":         "restore a volume",
    "scaleVirtualMachine":    "resize an instance (capacity repair)",
}


def sign(params, secret):
    """CloudStack request signing: sorted, lowercased, HMAC-SHA1, base64."""
    items = sorted((k, v) for k, v in params.items())
    query = urllib.parse.urlencode(items)
    to_sign = urllib.parse.urlencode(items).lower()
    digest = hmac.new(secret.encode(), to_sign.encode(), hashlib.sha1).digest()
    signature = urllib.parse.quote_plus(base64.b64encode(digest).decode())
    return f"{query}&signature={signature}"


def call(url, key, secret, command, **extra):
    params = {"command": command, "apikey": key, "response": "json"}
    params.update(extra)
    request = urllib.request.Request(f"{url}?{sign(params, secret)}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def main():
    url = os.environ.get("CS_URL")
    key = os.environ.get("CS_KEY")
    secret = os.environ.get("CS_SECRET")
    if not all([url, key, secret]):
        sys.exit("Set CS_URL, CS_KEY and CS_SECRET first. See the docstring.")

    print("1. Can this account sign a request at all?")
    try:
        result = call(url, key, secret, "listVirtualMachines")
        count = result.get("listvirtualmachinesresponse", {}).get("count", 0)
        print(f"   yes. {count} instance(s) visible.\n")
    except Exception as error:                      # noqa: BLE001
        sys.exit(f"   no. Signing or access failed: {error}\n"
                 f"   Check the URL ends in /client/api and the keys are current.")

    print("2. Which commands is this account permitted to call?")
    allowed = set()
    try:
        apis = call(url, key, secret, "listApis")["listapisresponse"]["api"]
        allowed = {a["name"] for a in apis}
        print(f"   {len(allowed)} commands available in total.\n")
    except Exception as error:                      # noqa: BLE001
        print(f"   listApis not available ({error}). Falling back to guessing.\n")

    print("3. What that means for the healer:\n")
    width = max(len(name) for name in WANTED)
    for name, why in sorted(WANTED.items()):
        if allowed:
            mark = "yes" if name in allowed else "NO "
        else:
            mark = " ? "
        print(f"   [{mark}] {name:<{width}}  {why}")

    missing = [n for n in WANTED if allowed and n not in allowed]
    print()
    if not allowed:
        print("   Could not confirm. Try each command manually before relying on it.")
    elif missing:
        print("   Not available, so these repairs cannot be automated here:")
        for name in missing:
            print(f"     - {name}: {WANTED[name]}")
        print("   Design the action catalogue around what is left, and record")
        print("   this constraint in the report as a platform limitation.")
    else:
        print("   Everything the healer needs is available, including rebuild.")
        print("   Keep destroyVirtualMachine behind an approval guardrail.")


if __name__ == "__main__":
    main()
