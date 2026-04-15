from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys

TOOLS_DIR = Path(__file__).resolve().parents[1] / "templates" / "repo" / "tools" / "openspec"
sys.path.insert(0, str(TOOLS_DIR))

import hook_common  # noqa: E402


def apply_ready_status() -> dict[str, object]:
    return {
        "applyRequires": ["tasks"],
        "artifacts": [{"id": "tasks", "status": "done"}],
    }


class HookCommonStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tempdir.name)
        patcher = mock.patch.object(hook_common, "REPO_ROOT", self.repo_root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tempdir.cleanup)

    def test_router_persists_selected_change_from_prompt(self) -> None:
        with mock.patch.object(
            hook_common,
            "openspec_list",
            return_value=[{"name": "foo"}, {"name": "bar"}],
        ):
            context = hook_common.build_router_context("请继续 foo 这个 change 并实现 handler")

        self.assertIn("foo", context)
        current_change = self.repo_root / ".openspec-auto" / "state" / "current_change.json"
        self.assertTrue(current_change.exists())
        self.assertEqual(json.loads(current_change.read_text())["name"], "foo")

    def test_guard_uses_persisted_change_when_multiple_active_changes_exist(self) -> None:
        state_dir = self.repo_root / ".openspec-auto" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "current_change.json").write_text(json.dumps({"name": "foo"}))

        with (
            mock.patch.object(
                hook_common,
                "openspec_list",
                return_value=[{"name": "foo"}, {"name": "bar"}],
            ),
            mock.patch.object(hook_common, "openspec_status", return_value=apply_ready_status()),
        ):
            allowed, reason = hook_common.should_allow_edit("Edit src/service.go")

        self.assertTrue(allowed)
        self.assertIn("foo", reason)

    def test_completion_blocks_when_multiple_changes_exist_but_none_selected(self) -> None:
        with (
            mock.patch.object(
                hook_common,
                "openspec_list",
                return_value=[{"name": "foo"}, {"name": "bar"}],
            ),
            mock.patch.object(hook_common, "git_changed_paths", return_value=["cmd/api/main.go"]),
        ):
            blocked, reason = hook_common.should_block_completion("已完成，测试通过")

        self.assertTrue(blocked)
        self.assertIn("choose", reason.lower())


if __name__ == "__main__":
    unittest.main()
