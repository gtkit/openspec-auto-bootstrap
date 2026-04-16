#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="${1:-}"

usage() {
  cat <<'EOF'
Usage:
  ./uninstall.sh /absolute/path/to/repo
EOF
}

die() {
  printf '[openspec-auto][error] %s\n' "$1" >&2
  exit 1
}

[[ -n "$REPO_DIR" ]] || { usage; exit 1; }
[[ -d "$REPO_DIR" ]] || die "Repo path does not exist: $REPO_DIR"
REPO_DIR="$(cd "$REPO_DIR" && pwd)"

remove_managed_block() {
  local dest="$1"
  python3 - "$dest" <<'PY'
from pathlib import Path
import re
import sys

dest = Path(sys.argv[1])
if not dest.exists():
    sys.exit(0)

content = dest.read_text()
pattern = re.compile(r"\n?<!-- OPENSPEC-AUTO:START -->.*?<!-- OPENSPEC-AUTO:END -->\n?", re.S)
updated = pattern.sub("\n", content).strip()
dest.write_text((updated + "\n") if updated else "")
PY
}

remove_path() {
  local target="$1"
  if [[ -e "$target" || -L "$target" ]]; then
    rm -rf "$target"
  fi
}

remove_managed_block "$REPO_DIR/AGENTS.md"
remove_managed_block "$REPO_DIR/CLAUDE.md"

remove_path "$REPO_DIR/.claude/hooks/openspec_context.py"
remove_path "$REPO_DIR/.claude/hooks/openspec_router.py"
remove_path "$REPO_DIR/.claude/hooks/openspec_guard.py"
remove_path "$REPO_DIR/.claude/hooks/openspec_stop.py"
remove_path "$REPO_DIR/.claude/skills/openspec-auto"
remove_path "$REPO_DIR/.agents/skills/openspec-auto"
remove_path "$REPO_DIR/.codex/hooks/openspec_context.py"
remove_path "$REPO_DIR/.codex/hooks/openspec_router.py"
remove_path "$REPO_DIR/.codex/hooks/openspec_guard.py"
remove_path "$REPO_DIR/.codex/hooks/openspec_stop.py"
remove_path "$REPO_DIR/.codex/prompts/openspec-auto.md"
remove_path "$REPO_DIR/.codex/config.toml.append"
remove_path "$REPO_DIR/tools/openspec/env.sh"
remove_path "$REPO_DIR/tools/openspec/healthcheck.sh"
remove_path "$REPO_DIR/tools/openspec/hook_common.py"
remove_path "$REPO_DIR/tools/openspec/classify_request.py"
remove_path "$REPO_DIR/tools/openspec/resolve_change.py"
remove_path "$REPO_DIR/tools/openspec/validate_repo.py"
remove_path "$REPO_DIR/tools/openspec/sync_templates.sh"
remove_path "$REPO_DIR/tools/openspec/__pycache__"
remove_path "$REPO_DIR/.openspec-auto"

python3 - "$REPO_DIR/.claude/settings.json" "$REPO_DIR/.codex/hooks.json" <<'PY'
from pathlib import Path
import json
import sys

paths = [Path(arg) for arg in sys.argv[1:]]
needle = "openspec_"

for path in paths:
    if not path.exists():
        continue
    data = json.loads(path.read_text())
    hooks = data.get("hooks", {})
    for event in list(hooks.keys()):
        filtered = []
        for entry in hooks[event]:
            commands = []
            for hook in entry.get("hooks", []):
                if needle not in hook.get("command", ""):
                    commands.append(hook)
            if commands:
                entry["hooks"] = commands
                filtered.append(entry)
        if filtered:
            hooks[event] = filtered
        else:
            hooks.pop(event, None)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
PY

if ! python3 - "$HOME/.codex/config.toml" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
if not path.exists():
    sys.exit(0)

text = path.read_text()
text = re.sub(r"\n?# OPENSPEC-AUTO:START.*?# OPENSPEC-AUTO:END\n?", "\n", text, flags=re.S)
text = re.sub(r"^\s*# OPENSPEC-AUTO: enable repo-local Codex hooks\s*$\n?", "", text, flags=re.M)
text = re.sub(r"^\s*codex_hooks\s*=\s*true\s*# openspec-auto\s*$\n?", "", text, flags=re.M)
try:
    path.write_text(text.rstrip() + "\n" if text.strip() else "")
except PermissionError:
    sys.exit(1)
PY
then
  printf '[openspec-auto][warn] Failed to clean ~/.codex/config.toml automatically. Remove openspec-auto markers manually if needed.\n' >&2
fi

# Remove directories if empty after cleanup
for dir in \
  "$REPO_DIR/.claude/hooks" \
  "$REPO_DIR/.claude/skills/openspec-auto" \
  "$REPO_DIR/.claude/skills" \
  "$REPO_DIR/.agents/skills/openspec-auto" \
  "$REPO_DIR/.agents/skills" \
  "$REPO_DIR/.agents" \
  "$REPO_DIR/.codex/hooks" \
  "$REPO_DIR/.codex/prompts" \
  "$REPO_DIR/tools/openspec" \
  "$REPO_DIR/tools"
do
  if [[ -d "$dir" ]] && [[ -z "$(ls -A "$dir" 2>/dev/null)" ]]; then
    rmdir "$dir" 2>/dev/null || true
  fi
done

cat <<EOF
Uninstall complete for:
  $REPO_DIR

OpenSpec artifacts under $REPO_DIR/openspec were left intact.
EOF
