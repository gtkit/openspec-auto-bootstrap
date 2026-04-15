#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR=""
FORCE=0
SKIP_CODEX_USER_CONFIG=0
SKIP_OPENSPEC_INIT=0

usage() {
  cat <<'EOF'
Usage:
  ./install.sh [options] /absolute/path/to/repo

Options:
  --force                   Overwrite managed files after backing them up
  --skip-codex-user-config  Do not modify ~/.codex/config.toml
  --skip-openspec-init      Do not run "openspec init --tools none"
  -h, --help                Show this help
EOF
}

log() {
  printf '[openspec-auto] %s\n' "$1"
}

warn() {
  printf '[openspec-auto][warn] %s\n' "$1" >&2
}

die() {
  printf '[openspec-auto][error] %s\n' "$1" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      FORCE=1
      shift
      ;;
    --skip-codex-user-config)
      SKIP_CODEX_USER_CONFIG=1
      shift
      ;;
    --skip-openspec-init)
      SKIP_OPENSPEC_INIT=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      die "Unknown option: $1"
      ;;
    *)
      if [[ -n "$REPO_DIR" ]]; then
        die "Only one repo path is allowed"
      fi
      REPO_DIR="$1"
      shift
      ;;
  esac
done

[[ -n "$REPO_DIR" ]] || die "Missing repo path"
[[ -d "$REPO_DIR" ]] || die "Repo path does not exist: $REPO_DIR"

REPO_DIR="$(cd "$REPO_DIR" && pwd)"
BACKUP_DIR="$REPO_DIR/.openspec-auto-backup/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

version_is_ok() {
  python3 - "$1" <<'PY'
import sys
from itertools import zip_longest

required = (20, 19, 0)
parts = tuple(int(p) for p in sys.argv[1].split("."))
for left, right in zip_longest(parts, required, fillvalue=0):
    if left > right:
        sys.exit(0)
    if left < right:
        sys.exit(1)
sys.exit(0)
PY
}

resolve_node_bin() {
  python3 - <<'PY'
import glob
import os
import shutil
import subprocess
import sys

def version_ok(version: str) -> bool:
    parts = tuple(int(p) for p in version.split("."))
    required = (20, 19, 0)
    padded = parts + (0,) * (3 - len(parts))
    return padded >= required

def node_version(path: str) -> str | None:
    try:
        result = subprocess.run([path, "-p", "process.versions.node"], text=True, capture_output=True, check=False)
    except OSError:
        return None
    version = result.stdout.strip()
    return version if result.returncode == 0 and version else None

candidates = []
for item in [os.environ.get("NODE_BIN"), shutil.which("node")]:
    if item:
        candidates.append(item)
candidates.extend(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")))

best = None
best_version = ()
for candidate in candidates:
    version = node_version(candidate)
    if not version or not version_ok(version):
        continue
    key = tuple(int(p) for p in version.split("."))
    if key > best_version:
        best = candidate
        best_version = key

if not best:
    sys.exit(1)

print(best)
PY
}

resolve_openspec_runner() {
  local openspec_path
  openspec_path="$(command -v openspec || true)"
  [[ -n "$openspec_path" ]] || die "Missing required command: openspec"

  if "$openspec_path" --version >/dev/null 2>&1; then
    OPEN_SPEC_CMD=("$openspec_path")
  else
    OPEN_SPEC_CMD=("$NODE_BIN" "$openspec_path")
    "${OPEN_SPEC_CMD[@]}" --version >/dev/null 2>&1 || die "Unable to run openspec with the resolved Node.js binary"
  fi
}

backup_path() {
  local target="$1"
  local base="$2"
  if [[ -e "$target" || -L "$target" ]]; then
    local rel="${target#"$base"/}"
    mkdir -p "$BACKUP_DIR/$(dirname "$rel")"
    cp -R "$target" "$BACKUP_DIR/$rel"
  fi
}

copy_file() {
  local src="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  if [[ -e "$dest" ]] && ! cmp -s "$src" "$dest"; then
    if [[ "$FORCE" -ne 1 ]]; then
      die "Managed file differs from the template: $dest. Re-run with --force to overwrite it."
    fi
  fi
  backup_path "$dest" "$REPO_DIR"
  cp "$src" "$dest"
}

upsert_managed_block() {
  local dest="$1"
  local block_file="$2"
  python3 - "$dest" "$block_file" <<'PY'
from pathlib import Path
import re
import sys

dest = Path(sys.argv[1])
block = Path(sys.argv[2]).read_text()
start = "<!-- OPENSPEC-AUTO:START -->"
end = "<!-- OPENSPEC-AUTO:END -->"
pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)

if dest.exists():
    content = dest.read_text()
else:
    content = ""

if pattern.search(content):
    new_content = pattern.sub(block.strip(), content)
elif content.strip():
    new_content = content.rstrip() + "\n\n" + block.strip() + "\n"
else:
    new_content = block.strip() + "\n"

dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(new_content)
PY
}

ensure_line_once() {
  local dest="$1"
  local line="$2"
  python3 - "$dest" "$line" <<'PY'
from pathlib import Path
import sys

dest = Path(sys.argv[1])
line = sys.argv[2]
if dest.exists():
    content = dest.read_text().splitlines()
else:
    content = []

if line not in content:
    content = [line, ""] + content

dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text("\n".join(content).rstrip() + "\n")
PY
}

merge_json() {
  local dest="$1"
  local src="$2"
  python3 - "$dest" "$src" <<'PY'
from pathlib import Path
import json
import sys

dest = Path(sys.argv[1])
src = Path(sys.argv[2])
incoming = json.loads(src.read_text())
if dest.exists():
    current = json.loads(dest.read_text())
else:
    current = {}

hooks = current.setdefault("hooks", {})
for event, entries in incoming.get("hooks", {}).items():
    bucket = hooks.setdefault(event, [])
    seen = {json.dumps(item, sort_keys=True) for item in bucket}
    for entry in entries:
        signature = json.dumps(entry, sort_keys=True)
        if signature not in seen:
            bucket.append(entry)
            seen.add(signature)

for key, value in incoming.items():
    if key == "hooks":
        continue
    current.setdefault(key, value)

dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n")
PY
}

patch_codex_user_config() {
  local config_path="$HOME/.codex/config.toml"
  mkdir -p "$(dirname "$config_path")"
  if [[ -e "$config_path" ]]; then
    backup_path "$config_path" "$HOME"
  fi
  python3 - "$config_path" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
marker_line = "codex_hooks = true # openspec-auto"
comment_line = "# OPENSPEC-AUTO: enable repo-local Codex hooks"

if path.exists():
    text = path.read_text()
else:
    text = ""

if marker_line in text:
    sys.exit(0)

if re.search(r"^\s*codex_hooks\s*=\s*true\b", text, re.M):
    sys.exit(0)

if re.search(r"^\[features\]\s*$", text, re.M):
    text = re.sub(
        r"^\[features\]\s*$",
        "[features]\n" + comment_line + "\n" + marker_line,
        text,
        count=1,
        flags=re.M,
    )
else:
    addition = "\n# OPENSPEC-AUTO:START\n[features]\n" + comment_line + "\n" + marker_line + "\n# OPENSPEC-AUTO:END\n"
    text = text.rstrip() + addition + ("\n" if text else "")

try:
    path.write_text(text if text.endswith("\n") else text + "\n")
except PermissionError:
    sys.exit(1)
PY
}

require_cmd python3
NODE_BIN="$(resolve_node_bin)" || die "Node.js must be >= 20.19.0"
version_is_ok "$("$NODE_BIN" -p 'process.versions.node')" || die "Node.js must be >= 20.19.0"
resolve_openspec_runner

if [[ ! -d "$REPO_DIR/.git" ]]; then
  warn "Target is not a git repository. The bootstrap still works, but production use is expected inside git."
fi

if [[ ! -d "$REPO_DIR/openspec" && "$SKIP_OPENSPEC_INIT" -eq 0 ]]; then
  log "Initializing OpenSpec structure in $REPO_DIR"
  OPENSPEC_TELEMETRY=0 "${OPEN_SPEC_CMD[@]}" init --tools none "$REPO_DIR" >/dev/null
fi

log "Installing managed text files"
backup_path "$REPO_DIR/AGENTS.md" "$REPO_DIR"
upsert_managed_block "$REPO_DIR/AGENTS.md" "$BOOTSTRAP_DIR/templates/repo/AGENTS.md"

backup_path "$REPO_DIR/CLAUDE.md" "$REPO_DIR"
ensure_line_once "$REPO_DIR/CLAUDE.md" "@AGENTS.md"
upsert_managed_block "$REPO_DIR/CLAUDE.md" "$BOOTSTRAP_DIR/templates/repo/CLAUDE.md"

log "Installing repo-local hook configs and skills"
copy_file "$BOOTSTRAP_DIR/templates/repo/.claude/hooks/openspec_context.py" "$REPO_DIR/.claude/hooks/openspec_context.py"
copy_file "$BOOTSTRAP_DIR/templates/repo/.claude/hooks/openspec_router.py" "$REPO_DIR/.claude/hooks/openspec_router.py"
copy_file "$BOOTSTRAP_DIR/templates/repo/.claude/hooks/openspec_guard.py" "$REPO_DIR/.claude/hooks/openspec_guard.py"
copy_file "$BOOTSTRAP_DIR/templates/repo/.claude/hooks/openspec_stop.py" "$REPO_DIR/.claude/hooks/openspec_stop.py"
copy_file "$BOOTSTRAP_DIR/templates/repo/.claude/skills/openspec-auto/SKILL.md" "$REPO_DIR/.claude/skills/openspec-auto/SKILL.md"
copy_file "$BOOTSTRAP_DIR/templates/repo/.agents/skills/openspec-auto/SKILL.md" "$REPO_DIR/.agents/skills/openspec-auto/SKILL.md"
copy_file "$BOOTSTRAP_DIR/templates/repo/.codex/hooks/openspec_context.py" "$REPO_DIR/.codex/hooks/openspec_context.py"
copy_file "$BOOTSTRAP_DIR/templates/repo/.codex/hooks/openspec_router.py" "$REPO_DIR/.codex/hooks/openspec_router.py"
copy_file "$BOOTSTRAP_DIR/templates/repo/.codex/hooks/openspec_guard.py" "$REPO_DIR/.codex/hooks/openspec_guard.py"
copy_file "$BOOTSTRAP_DIR/templates/repo/.codex/hooks/openspec_stop.py" "$REPO_DIR/.codex/hooks/openspec_stop.py"
copy_file "$BOOTSTRAP_DIR/templates/repo/.codex/prompts/openspec-auto.md" "$REPO_DIR/.codex/prompts/openspec-auto.md"
copy_file "$BOOTSTRAP_DIR/templates/repo/.codex/config.toml.append" "$REPO_DIR/.codex/config.toml.append"

copy_file "$BOOTSTRAP_DIR/templates/repo/tools/openspec/env.sh" "$REPO_DIR/tools/openspec/env.sh"
copy_file "$BOOTSTRAP_DIR/templates/repo/tools/openspec/healthcheck.sh" "$REPO_DIR/tools/openspec/healthcheck.sh"
copy_file "$BOOTSTRAP_DIR/templates/repo/tools/openspec/hook_common.py" "$REPO_DIR/tools/openspec/hook_common.py"
copy_file "$BOOTSTRAP_DIR/templates/repo/tools/openspec/classify_request.py" "$REPO_DIR/tools/openspec/classify_request.py"
copy_file "$BOOTSTRAP_DIR/templates/repo/tools/openspec/resolve_change.py" "$REPO_DIR/tools/openspec/resolve_change.py"
copy_file "$BOOTSTRAP_DIR/templates/repo/tools/openspec/validate_repo.py" "$REPO_DIR/tools/openspec/validate_repo.py"
copy_file "$BOOTSTRAP_DIR/templates/repo/tools/openspec/sync_templates.sh" "$REPO_DIR/tools/openspec/sync_templates.sh"

merge_json "$REPO_DIR/.claude/settings.json" "$BOOTSTRAP_DIR/templates/repo/.claude/settings.json"
merge_json "$REPO_DIR/.codex/hooks.json" "$BOOTSTRAP_DIR/templates/repo/.codex/hooks.json"

chmod +x \
  "$REPO_DIR/.claude/hooks/openspec_context.py" \
  "$REPO_DIR/.claude/hooks/openspec_router.py" \
  "$REPO_DIR/.claude/hooks/openspec_guard.py" \
  "$REPO_DIR/.claude/hooks/openspec_stop.py" \
  "$REPO_DIR/.codex/hooks/openspec_context.py" \
  "$REPO_DIR/.codex/hooks/openspec_router.py" \
  "$REPO_DIR/.codex/hooks/openspec_guard.py" \
  "$REPO_DIR/.codex/hooks/openspec_stop.py" \
  "$REPO_DIR/tools/openspec/env.sh" \
  "$REPO_DIR/tools/openspec/healthcheck.sh" \
  "$REPO_DIR/tools/openspec/sync_templates.sh"

if [[ "$SKIP_CODEX_USER_CONFIG" -eq 0 ]]; then
  log "Ensuring ~/.codex/config.toml enables repo-local hooks"
  if ! patch_codex_user_config; then
    warn "Failed to patch ~/.codex/config.toml automatically. Configure codex_hooks manually if needed."
  fi
else
  warn "Skipped ~/.codex/config.toml patch. You must enable codex_hooks manually."
fi

log "Running repo healthcheck"
"$REPO_DIR/tools/openspec/healthcheck.sh" "$REPO_DIR"

cat <<EOF

Install complete.

Repo:   $REPO_DIR
Backup: $BACKUP_DIR

Next:
  1. Open Claude Code or Codex in the repo root.
  2. Ask for a behavior-changing task normally, for example:
     - 实现订单超时自动取消
     - 修复支付回调重复入库
     - 把会员试用逻辑改成 7 天
  3. The repository will route the request through OpenSpec automatically.
EOF
