# Reproduce the EduCloud bank-statement lab

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
  masked credential entry below; never commit `.env` files or paste
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
python3 tools/lab_shell.py python3 tools/prepare_bank.py
python3 tools/lab_shell.py python3 tools/deploy_jobs.py
python3 tools/lab_shell.py python3 tools/provision_expansion.py probe-1
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
It performs ten occurrences per scenario: investigator approval, verified
manual repair with promotion, then automatic reuse. The operator is scripted
in this experiment; this does not substitute for a usability test with a person.

```sh
python3 tools/lab_shell.py python3 tools/demo_jobs_live.py --repetitions 10 --output state/bank-learning.json
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

The banking acceptance run on 16 October 2026 passed all 18 checks. Historical hashing-job trials do not validate the statement release. Run from `~/projects/bank-statements`; install Ubuntu's `python3-psycopg2` for database acceptance tests. Generated private client files and certificates must not enter Git.

`prepare_bank.py` must precede `deploy_jobs.py`: it provisions the synthetic schema, restricted roles and private TLS material. Provision the independent checker after the new client trust configuration exists. Deploy the updated database metrics collector too. Private CA lifetime is 365 days; leaf certificates are 90 days. Renewal is manual: plan it before expiry, preserve trust and revalidate deployment scope. Do not rerun preparation blindly over an established lab; back up first and inspect its schema/TLS changes.

The acceptance command `python3 tools/lab_shell.py python3 tools/test_bank_live.py --controlled-experiment` exercises authorisation, idempotency, TLS, immutable records and a restore into a separate scratch database. It never restores over the live ledger. `tools/bank_backup.py --label <fresh-label>` creates a PostgreSQL dump and consistent SQLite copies on the healer; copy this backup, private client configuration and PKI material to a protected laptop location. A dump on the same platform is not an off-platform backup. The initial restore-test cleanup exposed an unclosed connection; this was fixed and the complete run passed, so retain that finding alongside the successful evidence.

## Restore credentials after a healer host restart

Run as the loop user in a private SSH terminal. These prompts do not echo keys:

```sh
read -rp 'CloudStack URL: ' CS_URL
read -rsp 'CloudStack API key: ' CS_KEY; echo
read -rsp 'CloudStack secret: ' CS_SECRET; echo
read -rp 'Private SSH key path: ' LAB_SSH_KEY
export CS_URL CS_KEY CS_SECRET LAB_SSH_KEY
systemctl --user import-environment CS_URL CS_KEY CS_SECRET LAB_SSH_KEY
unset CS_URL CS_KEY CS_SECRET LAB_SSH_KEY
```

Optional Gemini credentials use the same masked prompt/import pattern. Never
paste secrets in chat or put them in Git. Private keys and scoped Kubernetes
credentials must already exist; this procedure does not recreate them.

## Current operational scope

Only seven VMs support job processing. app-1/app-2 are stopped and excluded
from all active scraping. The monitor helper replaces this project's active
configuration with job-only targets, archives prior files for rollback, and
provisions only the job dashboard. Do not run old experiment installers.
Historical files and detailed results stay in laptop archives. Recheck host
metrics as well as workload checks after any monitoring change.

## Fresh-deployment boundary

Base database provisioning creates PostgreSQL and the private database, then checks `pg_isready`. Statement schema/roles/TLS are created by the separate bank preparation phase; the contract exporter can report unready until that phase completes. The retired hashing role is optional and disabled when present; no hashing queue or deletion cron is created on a fresh host. Existing historical tables are preserved. The banking cutover was live tested on the existing seven-VM lab; a complete empty-project redeployment of all VMs has not been rehearsed.

## Recovery and key preservation

`bank_backup.py` includes the database dump, consistent controller SQLite copies, generated resource references, private database PKI/credentials and private healer clients/host pins. Its directory is mode 0700. Copy the complete directory to the protected laptop backup location and check archive readability; it contains private keys and must never be uploaded to GitHub. Cloud/model credentials held only in the service manager still need private re-entry after a host restart.

For a controller-only recovery, stop the controller and console, preserve the current state, restore matching `operator.db` and `knowledge.db` copies under `state/jobs`, and restore the private clients and reviewed references. Check resource identities against EduCloud before reconnecting. A replacement VM or changed reference requires revalidation; do not change host pins just to suppress an unexplained warning. Restart one controller only and verify fresh statements and every required check.

For a database incident, stop automatic changes and preserve the live database/evidence. Restore the dump into a separately named test database first and reconcile a previously acknowledged statement and the ledger. Do not overwrite the live database or replay an old backup over newly accepted requests through a healer recipe. Choosing a production restore point, handling newer accepted requests and any data-loss acceptance is an administrator-led recovery decision outside the automatic catalogue. The acceptance test proves a scratch restore; a complete replacement of every VM and private key has not been rehearsed.

Private API/database leaf certificates expire after 90 days. The dashboard alerts within 14 days of API certificate expiry; certificate renewal and trust redistribution remain an operator task. Keep the CA key in the private backup, restrict its access, renew before expiry and verify both endpoint identity and customer correctness afterward. Never use an insecure TLS fallback.

The read-only `check_bank_continuity.py` evaluates a consistent database snapshot. It compares completed statements with the exact oracle, verifies acceptance/completion audit counts and missing accepted records, and distinguishes newly pending work from requests older than the 30-second deadline. An in-flight request is not an incorrect completed statement.
