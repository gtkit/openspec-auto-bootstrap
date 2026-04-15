#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from json import JSONDecoder
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
OPEN_SPEC_ENV = {**os.environ, "OPENSPEC_TELEMETRY": os.environ.get("OPENSPEC_TELEMETRY", "0")}
DECODER = JSONDecoder()

READ_ONLY_PATTERNS = [
    r"\b(explain|analyze|review|summarize|summarise|describe|compare|why|how)\b",
    r"(解释|分析|审查|总结|说明|对比|为什么|怎么做)",
]
CHANGE_PATTERNS = [
    r"\b(add|build|change|create|fix|implement|modify|refactor|remove|rename|update|wire)\b",
    r"(实现|修复|修改|新增|增加|调整|重构|删除|改成|接入|联调|优化)",
]
SKIP_PATTERNS = [
    r"\b(skip openspec|without openspec)\b",
    r"(跳过\s*openspec|不用\s*openspec|不要\s*openspec)",
]
CODE_FILE_HINT = re.compile(r"\.(c|cc|cpp|cs|go|java|js|jsx|kt|mjs|php|py|rb|rs|sql|swift|ts|tsx|vue|yaml|yml)\b", re.I)
DOC_ONLY_HINT = re.compile(r"(^|/)(readme|docs?/|.*\.md$)", re.I)
COMPLETION_HINT = re.compile(r"\b(done|complete|completed|fixed|verified|all tests pass|ready)\b|(已完成|完成了|修复好了|验证通过|测试通过)")


def run_command(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    prefix = openspec_prefix() if args and args[0] == "openspec" else []
    return subprocess.run(
        prefix + args[1:] if prefix else args,
        cwd=str(cwd or REPO_ROOT),
        env=OPEN_SPEC_ENV,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def version_ok(version: str) -> bool:
    parts = tuple(int(p) for p in version.split("."))
    required = (20, 19, 0)
    padded = parts + (0,) * (3 - len(parts))
    return padded >= required


def resolve_node_bin() -> str | None:
    candidates: list[str] = []
    for item in [os.environ.get("NODE_BIN"), shutil.which("node")]:
        if item:
            candidates.append(item)
    candidates.extend(str(path) for path in Path.home().glob(".nvm/versions/node/*/bin/node"))

    best: str | None = None
    best_version: tuple[int, ...] = ()
    for candidate in candidates:
        try:
            result = subprocess.run(
                [candidate, "-p", "process.versions.node"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except OSError:
            continue
        version = result.stdout.strip()
        if result.returncode != 0 or not version or not version_ok(version):
            continue
        key = tuple(int(part) for part in version.split("."))
        if key > best_version:
            best = candidate
            best_version = key
    return best


def openspec_prefix() -> list[str]:
    openspec_path = os.environ.get("OPENSPEC_BIN") or shutil.which("openspec")
    if not openspec_path:
        return []
    direct = subprocess.run(
        [openspec_path, "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if direct.returncode == 0:
        return [openspec_path]
    node_bin = resolve_node_bin()
    if not node_bin:
        return [openspec_path]
    return [node_bin, openspec_path]


def extract_json_blob(text: str) -> Any | None:
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            value, _ = DECODER.raw_decode(text[index:])
            return value
        except json.JSONDecodeError:
            continue
    return None


def read_hook_payload() -> Any:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def flatten_strings(value: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for nested in value.values():
            strings.extend(flatten_strings(nested))
    elif isinstance(value, list):
        for nested in value:
            strings.extend(flatten_strings(nested))
    return strings


def summarize_payload(payload: Any) -> str:
    seen: list[str] = []
    for item in flatten_strings(payload):
        text = item.strip()
        if text and text not in seen:
            seen.append(text)
    return "\n".join(seen)


def classify_prompt(text: str) -> dict[str, Any]:
    normalized = text.lower()
    skip = any(re.search(pattern, normalized) for pattern in SKIP_PATTERNS)
    read_only = any(re.search(pattern, normalized) for pattern in READ_ONLY_PATTERNS)
    needs_change = any(re.search(pattern, normalized) for pattern in CHANGE_PATTERNS)
    needs_openspec = bool(needs_change and not skip)
    if read_only and not needs_change:
        needs_openspec = False
    return {
        "needs_openspec": needs_openspec,
        "skip_requested": skip,
        "read_only": read_only and not needs_change,
    }


def openspec_list() -> list[dict[str, Any]]:
    result = run_command(["openspec", "list", "--json"])
    payload = extract_json_blob(result.stdout)
    if isinstance(payload, dict):
        return payload.get("changes", []) or []
    return []


def openspec_status(change_name: str) -> dict[str, Any] | None:
    result = run_command(["openspec", "status", "--change", change_name, "--json"])
    payload = extract_json_blob(result.stdout)
    return payload if isinstance(payload, dict) else None


def validate_change(change_name: str) -> tuple[bool, dict[str, Any] | None]:
    result = run_command(
        ["openspec", "validate", change_name, "--type", "change", "--strict", "--json", "--no-interactive"]
    )
    payload = extract_json_blob(result.stdout)
    if isinstance(payload, dict):
        summary = payload.get("summary", {}).get("totals", {})
        return bool(summary.get("failed", 0) == 0 and result.returncode == 0), payload
    return result.returncode == 0, None


def select_change(prompt_text: str, changes: list[dict[str, Any]]) -> str | None:
    normalized = prompt_text.lower()
    names = [item.get("name", "") for item in changes if item.get("name")]
    for name in names:
        if name.lower() in normalized:
            return name
    return names[0] if len(names) == 1 else None


def is_apply_ready(status: dict[str, Any] | None) -> bool:
    if not status:
        return False
    needed = set(status.get("applyRequires", []))
    artifacts = {item.get("id"): item.get("status") for item in status.get("artifacts", [])}
    return bool(needed) and all(artifacts.get(item) == "done" for item in needed)


def git_changed_paths() -> list[str]:
    names: set[str] = set()
    for args in (
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only"],
    ):
        result = run_command(args)
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                names.add(line)
    return sorted(names)


def non_openspec_changes(paths: list[str]) -> list[str]:
    return [path for path in paths if not path.startswith("openspec/")]


def build_session_context() -> str:
    changes = openspec_list()
    if not changes:
        return (
            "OpenSpec repo mode is enabled in this repository.\n"
            "There are no active changes right now.\n"
            "If the user asks for behavior-changing work, use the project skill `openspec-auto` and create a change automatically."
        )
    bullet_lines = [f"- {item['name']} ({item.get('status', 'unknown')})" for item in changes if item.get("name")]
    return (
        "OpenSpec repo mode is enabled in this repository.\n"
        "Active changes:\n"
        + "\n".join(bullet_lines)
        + "\nUse the project skill `openspec-auto` for behavior-changing work and do not ask the user to type OpenSpec commands manually."
    )


def build_router_context(prompt_text: str) -> str | None:
    classification = classify_prompt(prompt_text)
    if not classification["needs_openspec"]:
        return None
    changes = openspec_list()
    selected = select_change(prompt_text, changes)
    if selected:
        return (
            "This request appears to change runtime behavior.\n"
            f"Route it through the project skill `openspec-auto` and prefer the active change `{selected}`.\n"
            "Do not ask the user to type OpenSpec commands manually."
        )
    if changes:
        names = ", ".join(item["name"] for item in changes if item.get("name"))
        return (
            "This request appears to change runtime behavior.\n"
            "Route it through the project skill `openspec-auto`.\n"
            f"Active changes exist: {names}. If more than one is plausible, ask the user to choose.\n"
            "Do not ask the user to type OpenSpec commands manually."
        )
    return (
        "This request appears to change runtime behavior.\n"
        "Route it through the project skill `openspec-auto`, create a new change automatically, and prepare it until apply-ready before editing application code.\n"
        "Do not ask the user to type OpenSpec commands manually."
    )


def should_allow_edit(payload_text: str) -> tuple[bool, str]:
    classification = classify_prompt(payload_text)
    if classification["skip_requested"]:
        return True, "User explicitly asked to bypass OpenSpec."
    if not payload_text.strip():
        return True, "No structured hook payload; fail open."
    if DOC_ONLY_HINT.search(payload_text) and not CODE_FILE_HINT.search(payload_text):
        return True, "Docs-only path detected."
    changes = openspec_list()
    if not changes:
        return False, "No active OpenSpec change exists yet."
    selected = select_change(payload_text, changes)
    if not selected:
        return False, "Multiple active changes exist and none could be chosen safely."
    status = openspec_status(selected)
    if is_apply_ready(status):
        return True, f"Change `{selected}` is apply-ready."
    return False, f"Change `{selected}` exists but is not apply-ready yet."


def should_block_completion(payload_text: str) -> tuple[bool, str]:
    if not COMPLETION_HINT.search(payload_text):
        return False, ""
    changed_paths = non_openspec_changes(git_changed_paths())
    changes = openspec_list()
    if changed_paths and not changes:
        preview = ", ".join(changed_paths[:5])
        return True, f"Code changed outside openspec/ but there is no active OpenSpec change. Files: {preview}"
    selected = select_change(payload_text, changes)
    if selected:
        valid, payload = validate_change(selected)
        if not valid:
            issues: list[str] = []
            if isinstance(payload, dict):
                for item in payload.get("items", []):
                    for issue in item.get("issues", []):
                        issues.append(issue.get("message", "validation failed"))
            detail = issues[0] if issues else "OpenSpec validation failed."
            return True, f"Completion is blocked because change `{selected}` is not valid: {detail}"
    return False, ""


def emit_response(
    *,
    event_name: str,
    additional_context: str | None = None,
    permission_decision: str | None = None,
    continue_value: bool | None = None,
    stop_reason: str | None = None,
) -> None:
    payload: dict[str, Any] = {}
    if permission_decision:
        payload["permissionDecision"] = permission_decision
    if continue_value is not None:
        payload["continue"] = continue_value
    if stop_reason:
        payload["stopReason"] = stop_reason
    if additional_context:
        if os.getenv("CLAUDE_PLUGIN_ROOT") and not os.getenv("COPILOT_CLI"):
            payload["hookSpecificOutput"] = {
                "hookEventName": event_name,
                "additionalContext": additional_context,
            }
        else:
            payload["additionalContext"] = additional_context
    print(json.dumps(payload, ensure_ascii=False))
