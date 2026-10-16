#!/usr/bin/env bash
# Shared engine safety plus the only supported application and operator console.
set -euo pipefail
cd "$(dirname "$0")/.."
for suite in safety learning adapter operator jobs banking console; do
  python3 "tools/test_${suite}.py"
done
while IFS= read -r -d '' script; do bash -n "$script"; done < <(find tools -name '*.sh' -print0)
python3 -m compileall -q mapek tools monitoring
