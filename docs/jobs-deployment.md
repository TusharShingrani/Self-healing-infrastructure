# Reproduce the EduCloud job-service lab

This is a lab deployment procedure, not a generic enterprise installer. It
creates five supporting VMs and requires an existing healer, private network,
monitor and approved CloudStack quota. Read the configured resource sizes and
available quota before deploying. The application uses synthetic data only.

## Requirements

- Ubuntu healer with Python 3, working pinned SSH to the isolated network,
  registered lab key and HTTPS-verified CloudStack access.
- `config/lab.json` identifies the project, network, baseline Ubuntu template,
  zone and keypair. `config/jobs-lab.json` identifies the five nodes and offerings.
- Credentials are in the loop user's service-manager environment. Use the
  existing masked credential entry workflow; never commit `.env` files or paste
  keys into the console. `tools/lab_shell.py` inherits the existing credentials.
- `state/expansion.json` preserves deployed identities. Do not discard it and
  silently adopt machines by name. Repeated deployment refuses disappeared
  recorded VMs and occupied addresses.

## Ordered installation

Run on the healer from the intended checkout. These operations allocate and
configure private lab resources; they are not a read-only preview.

```sh
python3 tools/lab_shell.py python3 tools/expansion.py deploy
python3 tools/lab_shell.py python3 tools/provision_expansion.py k8s-control
python3 tools/lab_shell.py python3 tools/provision_expansion.py k8s-worker-1
python3 tools/lab_shell.py python3 tools/provision_expansion.py k8s-worker-2
python3 tools/lab_shell.py python3 tools/provision_expansion.py db-1
python3 tools/lab_shell.py python3 tools/provision_expansion.py probe-1
python3 tools/lab_shell.py python3 tools/deploy_jobs.py
python3 tools/lab_shell.py python3 tools/jobs.py status
bash tools/start_jobs.sh start
python3 tools/lab_shell.py python3 tools/configure_jobs_monitor.py
```

The deployment creates private credentials, a scoped Kubernetes API client,
public reference manifests and image metadata. Private generated files stay on
their machines, outside Git. The exact control forwarding source is checked;
different cluster networking requires investigation rather than widening a
CIDR until traffic works. Do not rerun deployment during an experiment: it
restores desired state and changes verification scope.

The scoped healer Kubernetes token is currently minted for 720 hours. Renew it
through the reviewed deployment/credential workflow before expiry; automatic
token renewal is not implemented. Expiry is an outage to detect, not permission
to fall back to cluster-admin. Back up state, references, private credentials,
host pins and a database dump privately off-platform. Restoring only source
code does not restore job data or learned procedures.

Install the [console](web-console.md), then verify current independent jobs,
all required checks and all Prometheus targets before fault injection. Check
each service's actual working directory to avoid running two controllers.

## Controlled evaluation

Run all offline tests first. The default live exercise covers only database
endpoint drift, worker capacity drift and worker memory configuration drift.
It performs three occurrences per scenario: investigator approval, verified
manual repair with promotion, then automatic reuse. The operator is scripted
in this experiment; this does not substitute for a usability test with a person.

```sh
python3 tools/lab_shell.py python3 tools/demo_jobs_live.py --output evidence/jobs-final-learning.json
```

It refuses to overwrite evidence or pretend to learn a procedure that is
already validated in the same scope. Preserve existing Knowledge; use an
explicitly planned separate experimental state rather than deleting history.
Normal rate limits and cooldowns remain active. Observe-only mode keeps metrics
available while the experiment driver owns actions. A failed exercise retains
its failure and attempts cleanup; verify the final state yourself.

The optional `--fault network` security exercise is confined to the owned
application's private policy and a fixed unrelated lab endpoint. It is not a
public scan. Database stop and worker-VM stop remain explicit supporting
diagnostics, excluded from the default research sequence.

Final live evidence still needs to be collected after EduCloud access is
restored. Do not substitute earlier cached-verification pilot results.
