# Aborted run: do not use these results

Stopped at 16:07:35Z when provisioning app-1 for rep 1 config B failed with
"Could not get lock /var/lib/apt/lists/lock": cloud-init on the fresh instance
still held the apt lock. Installers now wait for cloud-init and the apt locks.

results.csv in this folder is also wrong in one row: "rep 1 config A repeat"
points at a run on app-2 (a separate effector check started by hand during the
experiment), because the orchestrator took "the newest run folder". The real
config A repeat run is evidence/runs/2026-10-13T160014Z-app-1-disk_leak-A
(180 s down, the whole window). The orchestrator now uses the folder that
live_run.py reports and checks that it is a run on app-1.

The experiment was restarted from scratch.
