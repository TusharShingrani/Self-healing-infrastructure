#!/usr/bin/env bash
# Independent entry points: some historical suites execute checks at import.
set -euo pipefail
cd "$(dirname "$0")/.."
for suite in safety learning adapter operator infrastructure transaction repository jobs console; do
  python3 "tools/test_${suite}.py"
done
bash tools/test_lab_host.sh
while IFS= read -r -d '' script; do bash -n "$script"; done < <(find tools -name '*.sh' -print0)
for script in tools/lab-host/*; do bash -n "$script"; done
python3 -m compileall -q mapek tools monitoring
