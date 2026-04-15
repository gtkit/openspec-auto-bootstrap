#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from hook_common import extract_json_blob, non_openspec_changes, openspec_list, run_command


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.getcwd())
    parser.add_argument("--ci", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    os.chdir(repo)

    changes = openspec_list()
    changed = non_openspec_changes(
        [line.strip() for line in run_command(["git", "diff", "--name-only"]).stdout.splitlines() if line.strip()]
    )

    report = {
        "repo": str(repo),
        "activeChanges": [item.get("name") for item in changes if item.get("name")],
        "changedOutsideOpenSpec": changed,
        "ok": True,
        "messages": [],
    }

    if args.smoke:
      print(json.dumps(report, ensure_ascii=False, indent=2))
      return 0

    if changed and not changes:
        report["ok"] = False
        report["messages"].append("Code changed outside openspec/ but no active OpenSpec change exists.")

    if changes:
        result = run_command(["openspec", "validate", "--changes", "--strict", "--json", "--no-interactive"], cwd=repo)
        payload = extract_json_blob(result.stdout) or {}
        failed = payload.get("summary", {}).get("totals", {}).get("failed", 0)
        if result.returncode != 0 or failed:
            report["ok"] = False
            report["messages"].append("OpenSpec validation failed for one or more active changes.")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] or not args.ci else 1


if __name__ == "__main__":
    raise SystemExit(main())
