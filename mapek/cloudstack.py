"""Minimal Apache CloudStack client for EduCloud.

Only what the healer needs: signed requests, project scoping, and waiting for
asynchronous jobs. No dependencies.

Lessons from the lab that are baked in here:
  - spaces must be encoded as %20, not +, or the signature is rejected
  - list calls must be scoped with projectid, or they return nothing
  - deploy, stop, start and revert are asynchronous: the call returns a job id
    and the work happens later, so every one of them must be waited on
  - a snapshot record left in Error state blocks a later restore, and it can
    only be deleted while the instance is running
"""

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


class CloudStackError(RuntimeError):
    pass


class CloudStack:
    def __init__(self, url=None, key=None, secret=None, project=None, timeout=30):
        self.url = url or os.environ.get("CS_URL")
        self.key = key or os.environ.get("CS_KEY")
        self.secret = secret or os.environ.get("CS_SECRET")
        # Name every missing variable at once, never a value.
        missing = [name for name, value in (("CS_URL", self.url),
                                            ("CS_KEY", self.key),
                                            ("CS_SECRET", self.secret))
                   if not value]
        if missing:
            raise CloudStackError("missing credentials in the environment: "
                                  + ", ".join(missing))
        # Catch a value pasted with its own name, such as "CS_URL=https://...".
        # Report the shape of the mistake, never the value.
        if not self.url.startswith("https://"):
            hint = (" (it begins with 'CS_URL=', the value was pasted with its name)"
                    if self.url.upper().startswith("CS_URL=") else "")
            raise CloudStackError("CS_URL must begin with https://" + hint)
        self.project = project or os.environ.get("CS_PROJECT")
        self.timeout = timeout

    # ---------------------------------------------------------------- core

    def _sign(self, params):
        items = sorted((k, str(v)) for k, v in params.items())
        query = urllib.parse.urlencode(items, quote_via=urllib.parse.quote)
        digest = hmac.new(self.secret.encode(), query.lower().encode(),
                          hashlib.sha1).digest()
        signature = urllib.parse.quote(base64.b64encode(digest).decode())
        return f"{query}&signature={signature}"

    def call(self, command, scoped=True, **params):
        params.update({"command": command, "apikey": self.key, "response": "json"})
        if scoped and self.project and "projectid" not in params:
            params["projectid"] = self.project
        request = urllib.request.Request(f"{self.url}?{self._sign(params)}")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            body = error.read().decode()[:400]
            raise CloudStackError(f"{command} failed: {error.code} {body}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            # A network failure is not an empty answer. Report it, and never
            # echo the signed URL, which carries the API key.
            reason = getattr(error, "reason", error)
            raise CloudStackError(f"{command} could not reach the API: {reason}") from None
        key = command.lower() + "response"
        return payload.get(key, payload)

    def wait(self, response, label="job", poll=5, limit=900):
        """Block until an asynchronous job finishes. Returns its result."""
        job_id = response.get("jobid")
        if not job_id:
            return response
        deadline = time.time() + limit
        while time.time() < deadline:
            result = self.call("queryAsyncJobResult", jobid=job_id, scoped=False)
            status = result.get("jobstatus")
            if status == 1:
                return result.get("jobresult", {})
            if status == 2:
                reason = result.get("jobresult", {}).get("errortext", "unknown")
                raise CloudStackError(f"{label} failed: {reason}")
            time.sleep(poll)
        raise CloudStackError(f"{label} did not finish within {limit}s")

    # ------------------------------------------------------------- reading

    def instances(self, **filters):
        result = self.call("listVirtualMachines", **filters)
        return result.get("virtualmachine", [])

    def instance(self, name):
        for vm in self.instances():
            if vm.get("name") == name:
                return vm
        return None

    def ip_of(self, vm):
        nics = vm.get("nic") or []
        return nics[0].get("ipaddress") if nics else None

    def templates(self):
        return self.call("listTemplates", templatefilter="self").get("template", [])

    # ------------------------------------------------------------- writing

    def deploy(self, name, template_id, zone_id, offering_id, network_id,
               keypair=None, ipaddress=None):
        params = {
            "name": name, "displayname": name,
            "templateid": template_id, "zoneid": zone_id,
            "serviceofferingid": offering_id, "networkids": network_id,
        }
        if keypair:
            params["keypair"] = keypair
        if ipaddress:
            # a fixed address on the isolated network, so a rebuilt instance
            # comes back where Prometheus and the healer expect it
            params["ipaddress"] = ipaddress
        return self.wait(self.call("deployVirtualMachine", **params),
                         f"deploy {name}")

    def stop(self, vm_id, forced=False):
        return self.wait(self.call("stopVirtualMachine", id=vm_id,
                                   forced=str(bool(forced)).lower()), "stop")

    def start(self, vm_id):
        return self.wait(self.call("startVirtualMachine", id=vm_id), "start")

    def reboot(self, vm_id):
        return self.wait(self.call("rebootVirtualMachine", id=vm_id), "reboot")

    def destroy(self, vm_id, expunge=True):
        return self.wait(self.call("destroyVirtualMachine", id=vm_id,
                                   expunge=str(bool(expunge)).lower()), "destroy")

    def revert(self, snapshot_id):
        """Revert a volume snapshot. The instance must be stopped first.

        If this returns error 431, look for a snapshot record in Error state:
        it has to be deleted, and deletion only works while the instance is
        running. Start, delete the record, stop, then revert.
        """
        return self.wait(self.call("revertSnapshot", id=snapshot_id), "revert")
