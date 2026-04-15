#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="${1:-}"

if [[ -z "$REPO_DIR" ]]; then
  cat <<EOF
Bootstrap directory looks present:
  $BOOTSTRAP_DIR

Pass a repo path to run the full healthcheck:
  $BOOTSTRAP_DIR/doctor.sh /absolute/path/to/repo
EOF
  exit 0
fi

REPO_DIR="$(cd "$REPO_DIR" && pwd)"
"$REPO_DIR/tools/openspec/healthcheck.sh" "$REPO_DIR"
