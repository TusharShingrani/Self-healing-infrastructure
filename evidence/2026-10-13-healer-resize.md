# Healer resized in place, 2026-10-13

The user requested more CPU and RAM after the memory-pressure incident.
The loop was already inactive and no live experiment process was running.
The healer was backed up to the laptop before the stop/resize/start operation.
The readable archive includes the project and Git history, runtime state,
lab and GitHub keys, pinned host keys, registry and Claude project data.
Private backup contents stay off GitHub.

## Observed after the resize

- Same instance id: `41e8e0db-9207-4dd0-822c-bc3b74cb991e`.
- Same guest IP: `10.1.1.205`; same gateway: `10.53.14.225:22`.
- Offering: Small Instance ++, `5e2e56b0-5ce6-4966-9463-7c88a1419a72`.
- Portal: 2 CPUs and 6144 MB memory. Guest: `nproc` reports 2;
  `free -h` reports about 5.8 GiB RAM.
- Added a 1 GiB swap file, mode 0600, active with `swapon` and configured
  once in `/etc/fstab`. `findmnt --verify` reports no parse errors or errors;
  systemd was reloaded after the fstab change. Persistence is configured;
  no second reboot was performed to test it.
- The VPN address changed to 172.16.16.15. The existing firewall permitted
  only 172.16.16.2/32. With explicit user approval, TCP 22 was added for
  172.16.16.15/32. Laptop SSH was then verified.
- The healer regenerated its host key at startup. Its ED25519 fingerprint
  was checked in the authenticated EduCloud console, then compared with the
  key presented over the network before updating the local pin:
  `SHA256:ReQ7YObQys1Xcq8ByoXAFCobvNgrmDCHSAhrwopCHUg`.
- Downloads `healer-lab-key2.key`, the remote lab private key and the
  backed-up private key have matching public fingerprints. No keys were
  changed or re-registered. The healer's own CloudStack keypair is still
  `healer-lab-key`; app and monitor deployment uses `healer-lab-key2`.
- Safety: 18 passed; adapter: 66 passed; learning: 36 passed; host scripts:
  39 passed. All were run on the resized healer and none reported failures.
- Both app `/healthz` endpoints answer `ok`. Pinned SSH to both apps and
  the monitor works. Grafana `/api/health` reports database `ok`.
- GitHub `git push --dry-run` reports everything up to date before these
  documentation changes.

## Evidence boundary and remaining work

These checks establish that the resized guest and its internal connections
work. They do not constitute another fault experiment. Target app sizes
remain 1 CPU / 1 GiB; monitor remains 1 CPU / 4 GiB.

The loop is stopped. API credentials were deliberately held in memory and
are gone after the reboot. Re-enter them without storing them, run
`python3 tools/lab.py status`, start the loop with `start_loop.sh`, and check
the loop metrics and Prometheus scrape before another experiment.
The invalid A repeat remains excluded. Missing B/C repetitions have not
been rerun and existing results have not been rewritten.
