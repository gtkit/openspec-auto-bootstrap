#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/env.sh"

REPO_DIR="${1:-$(openspec_repo_root)}"
REPO_DIR="$(cd "$REPO_DIR" && pwd)"

printf '[openspec-auto] healthcheck repo=%s\n' "$REPO_DIR"

openspec_require_cmd python3
RUNNER="$(openspec_resolve_runner)"
NODE_BIN="$(openspec_resolve_node_bin)"

node_version="$("$NODE_BIN" -p 'process.versions.node' 2>/dev/null || true)"
python3 - "$node_version" <<'PY'
import sys
from itertools import zip_longest

required = (20, 19, 0)
parts = tuple(int(p) for p in sys.argv[1].split(".")) if sys.argv[1] else ()
for left, right in zip_longest(parts, required, fillvalue=0):
    if left > right:
        sys.exit(0)
    if left < right:
        print("[openspec-auto][error] Node.js must be >= 20.19.0", file=sys.stderr)
        sys.exit(1)
sys.exit(0)
PY

(
  cd "$REPO_DIR"
  OPENSPEC_TELEMETRY=0 bash -lc "$RUNNER list --json >/dev/null"
)

python3 "$REPO_DIR/tools/openspec/validate_repo.py" --repo "$REPO_DIR" --smoke

if command -v claude >/dev/null 2>&1; then
  printf '[openspec-auto] claude=%s\n' "$(claude -v 2>/dev/null || printf 'unknown')"
else
  printf '[openspec-auto] claude=missing (warning)\n'
fi

if command -v codex >/dev/null 2>&1; then
  printf '[openspec-auto] codex=present\n'
else
  printf '[openspec-auto] codex=missing (warning)\n'
fi

printf '[openspec-auto] healthcheck passed\n'
