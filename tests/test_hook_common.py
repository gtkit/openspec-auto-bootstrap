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

    def test_router_routes_edit_file_request(self) -> None:
        """build_router_context should route 'edit package.json' through OpenSpec."""
        with mock.patch.object(hook_common, "openspec_list", return_value=[]):
            context = hook_common.build_router_context("edit package.json scripts")
        self.assertIsNotNone(context)
        self.assertIn("behavior", context)

    def test_router_skips_read_only_request(self) -> None:
        context = hook_common.build_router_context("explain how the auth middleware works")
        self.assertIsNone(context)

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


class ClassifyPromptTests(unittest.TestCase):
    def test_read_only_english(self) -> None:
        result = hook_common.classify_prompt("explain how the auth middleware works")
        self.assertFalse(result["needs_openspec"])
        self.assertTrue(result["read_only"])

    def test_read_only_chinese(self) -> None:
        result = hook_common.classify_prompt("解释一下这个中间件怎么工作的")
        self.assertFalse(result["needs_openspec"])
        self.assertTrue(result["read_only"])

    def test_behavior_changing_english(self) -> None:
        result = hook_common.classify_prompt("implement user login feature")
        self.assertTrue(result["needs_openspec"])

    def test_behavior_changing_chinese(self) -> None:
        result = hook_common.classify_prompt("实现用户登录功能")
        self.assertTrue(result["needs_openspec"])

    def test_skip_requested(self) -> None:
        result = hook_common.classify_prompt("fix the bug skip openspec")
        self.assertTrue(result["skip_requested"])
        self.assertFalse(result["needs_openspec"])

    def test_build_and_run_tests_not_change(self) -> None:
        result = hook_common.classify_prompt("build and run the tests")
        self.assertFalse(result["needs_openspec"])

    def test_run_tests_not_change(self) -> None:
        result = hook_common.classify_prompt("run the test suite")
        self.assertFalse(result["needs_openspec"])

    def test_create_pr_not_change(self) -> None:
        result = hook_common.classify_prompt("create a PR for this branch")
        self.assertFalse(result["needs_openspec"])

    def test_create_pull_request_not_change(self) -> None:
        result = hook_common.classify_prompt("create a new pull request")
        self.assertFalse(result["needs_openspec"])

    def test_add_comment_not_change(self) -> None:
        result = hook_common.classify_prompt("add a comment explaining this function")
        self.assertFalse(result["needs_openspec"])

    def test_real_change_still_detected(self) -> None:
        result = hook_common.classify_prompt("add a new payment handler for Stripe")
        self.assertTrue(result["needs_openspec"])

    def test_fix_still_detected(self) -> None:
        result = hook_common.classify_prompt("fix the payment callback duplicate issue")
        self.assertTrue(result["needs_openspec"])

    # --- Expanded intent patterns (issue #3) ---

    def test_support_csv_export(self) -> None:
        result = hook_common.classify_prompt("支持导出 CSV")
        self.assertTrue(result["needs_openspec"])

    def test_switch_to_redis(self) -> None:
        result = hook_common.classify_prompt("switch to redis cache")
        self.assertTrue(result["needs_openspec"])

    def test_migrate_login_to_sso(self) -> None:
        result = hook_common.classify_prompt("把登录逻辑迁到 SSO")
        self.assertTrue(result["needs_openspec"])

    def test_enable_feature_flag(self) -> None:
        result = hook_common.classify_prompt("enable the dark mode feature flag")
        self.assertTrue(result["needs_openspec"])

    def test_replace_mysql_with_postgres(self) -> None:
        result = hook_common.classify_prompt("replace MySQL with Postgres")
        self.assertTrue(result["needs_openspec"])

    def test_integrate_with_stripe(self) -> None:
        result = hook_common.classify_prompt("integrate with Stripe payments")
        self.assertTrue(result["needs_openspec"])

    def test_expose_as_api(self) -> None:
        result = hook_common.classify_prompt("expose this as a REST API")
        self.assertTrue(result["needs_openspec"])

    def test_split_into_microservices(self) -> None:
        result = hook_common.classify_prompt("split the monolith into microservices")
        self.assertTrue(result["needs_openspec"])

    def test_upgrade_dependency(self) -> None:
        result = hook_common.classify_prompt("upgrade the gorm dependency to v2")
        self.assertTrue(result["needs_openspec"])

    def test_chinese_encapsulate(self) -> None:
        result = hook_common.classify_prompt("封装一个通用的分页组件")
        self.assertTrue(result["needs_openspec"])

    def test_chinese_introduce(self) -> None:
        result = hook_common.classify_prompt("引入 Redis 做缓存")
        self.assertTrue(result["needs_openspec"])

    def test_chinese_switch(self) -> None:
        result = hook_common.classify_prompt("切换到新的认证方式")
        self.assertTrue(result["needs_openspec"])

    # --- edit/write/delete/patch verbs (issue: router routing) ---

    def test_edit_script_is_change(self) -> None:
        result = hook_common.classify_prompt("edit scripts/release.sh")
        self.assertTrue(result["needs_openspec"])

    def test_edit_config_is_change(self) -> None:
        result = hook_common.classify_prompt("edit package.json scripts")
        self.assertTrue(result["needs_openspec"])

    def test_write_new_entrypoint_is_change(self) -> None:
        result = hook_common.classify_prompt("write a new entrypoint.sh")
        self.assertTrue(result["needs_openspec"])

    def test_delete_endpoint_is_change(self) -> None:
        result = hook_common.classify_prompt("delete the deprecated /v1/users endpoint")
        self.assertTrue(result["needs_openspec"])

    def test_patch_config_is_change(self) -> None:
        result = hook_common.classify_prompt("patch the nginx config for rate limiting")
        self.assertTrue(result["needs_openspec"])

    def test_rewrite_auth_is_change(self) -> None:
        result = hook_common.classify_prompt("rewrite the auth middleware")
        self.assertTrue(result["needs_openspec"])

    # --- false positive exclusions for edit/write/delete ---

    def test_write_comment_not_change(self) -> None:
        result = hook_common.classify_prompt("write a comment explaining this function")
        self.assertFalse(result["needs_openspec"])

    def test_edit_readme_not_change(self) -> None:
        result = hook_common.classify_prompt("edit the readme to update badges")
        self.assertFalse(result["needs_openspec"])

    def test_edit_docs_not_change(self) -> None:
        result = hook_common.classify_prompt("edit the documentation for this API")
        self.assertFalse(result["needs_openspec"])

    def test_delete_branch_not_change(self) -> None:
        result = hook_common.classify_prompt("delete the feature branch")
        self.assertFalse(result["needs_openspec"])


class ShouldAllowEditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tempdir.name)
        patcher = mock.patch.object(hook_common, "REPO_ROOT", self.repo_root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tempdir.cleanup)

    def test_read_only_bash_allowed_without_calling_openspec(self) -> None:
        """Read-only Bash commands should short-circuit without querying OpenSpec."""
        with mock.patch.object(hook_common, "openspec_list", side_effect=RuntimeError("should not be called")):
            allowed, reason = hook_common.should_allow_edit("git log --oneline")
        self.assertTrue(allowed)

    def test_ls_command_allowed(self) -> None:
        with mock.patch.object(hook_common, "openspec_list", side_effect=RuntimeError("should not be called")):
            allowed, reason = hook_common.should_allow_edit("ls -la src/")
        self.assertTrue(allowed)

    def test_npm_test_allowed(self) -> None:
        with mock.patch.object(hook_common, "openspec_list", side_effect=RuntimeError("should not be called")):
            allowed, reason = hook_common.should_allow_edit("npm test")
        self.assertTrue(allowed)

    def test_code_file_edit_blocked_without_active_change(self) -> None:
        """Edit of .go file should be blocked when no active change exists."""
        with mock.patch.object(hook_common, "openspec_list", return_value=[]):
            allowed, reason = hook_common.should_allow_edit("Edit src/main.go")
        self.assertFalse(allowed)

    def test_docs_only_edit_allowed(self) -> None:
        allowed, _ = hook_common.should_allow_edit("Edit README.md adding docs")
        self.assertTrue(allowed)

    def test_skip_openspec_allows_edit(self) -> None:
        allowed, _ = hook_common.should_allow_edit("skip openspec and edit main.go")
        self.assertTrue(allowed)

    # --- Config file guard tests (issue #2) ---

    def test_makefile_edit_blocked_without_active_change(self) -> None:
        with mock.patch.object(hook_common, "openspec_list", return_value=[]):
            allowed, _ = hook_common.should_allow_edit("Edit Makefile deploy target")
        self.assertFalse(allowed)

    def test_config_toml_edit_blocked_without_active_change(self) -> None:
        with mock.patch.object(hook_common, "openspec_list", return_value=[]):
            allowed, _ = hook_common.should_allow_edit("Edit config.toml to enable feature flag")
        self.assertFalse(allowed)

    def test_package_json_edit_blocked_without_active_change(self) -> None:
        with mock.patch.object(hook_common, "openspec_list", return_value=[]):
            allowed, _ = hook_common.should_allow_edit("Edit package.json scripts")
        self.assertFalse(allowed)

    def test_dockerfile_edit_blocked_without_active_change(self) -> None:
        with mock.patch.object(hook_common, "openspec_list", return_value=[]):
            allowed, _ = hook_common.should_allow_edit("Edit Dockerfile")
        self.assertFalse(allowed)

    def test_env_file_edit_blocked_without_active_change(self) -> None:
        with mock.patch.object(hook_common, "openspec_list", return_value=[]):
            allowed, _ = hook_common.should_allow_edit("Write .env DB_HOST=localhost")
        self.assertFalse(allowed)

    def test_terraform_edit_blocked_without_active_change(self) -> None:
        with mock.patch.object(hook_common, "openspec_list", return_value=[]):
            allowed, _ = hook_common.should_allow_edit("Edit infra/main.tf")
        self.assertFalse(allowed)

    def test_shell_script_edit_blocked_without_active_change(self) -> None:
        with mock.patch.object(hook_common, "openspec_list", return_value=[]):
            allowed, _ = hook_common.should_allow_edit("Edit scripts/release.sh")
        self.assertFalse(allowed)

    def test_shell_script_write_blocked_without_active_change(self) -> None:
        with mock.patch.object(hook_common, "openspec_list", return_value=[]):
            allowed, _ = hook_common.should_allow_edit("Write entrypoint.sh")
        self.assertFalse(allowed)

    def test_bash_script_edit_blocked(self) -> None:
        with mock.patch.object(hook_common, "openspec_list", return_value=[]):
            allowed, _ = hook_common.should_allow_edit("Edit deploy.bash")
        self.assertFalse(allowed)


class SelectChangeTests(unittest.TestCase):
    def test_prefers_longest_match(self) -> None:
        changes = [{"name": "api"}, {"name": "api-gateway"}]
        result = hook_common.select_change("update the api-gateway handler", changes)
        self.assertEqual(result, "api-gateway")

    def test_single_change_auto_selected(self) -> None:
        changes = [{"name": "user-login"}]
        result = hook_common.select_change("some unrelated prompt", changes)
        self.assertEqual(result, "user-login")

    def test_no_match_multiple_changes_returns_none(self) -> None:
        changes = [{"name": "foo"}, {"name": "bar"}]
        result = hook_common.select_change("some unrelated prompt", changes)
        self.assertIsNone(result)

    def test_exact_name_match(self) -> None:
        changes = [{"name": "order-timeout"}, {"name": "payment-fix"}]
        result = hook_common.select_change("continue working on order-timeout", changes)
        self.assertEqual(result, "order-timeout")


class VersionOkTests(unittest.TestCase):
    def test_exact_minimum(self) -> None:
        self.assertTrue(hook_common.version_ok("20.19.0"))

    def test_above_minimum(self) -> None:
        self.assertTrue(hook_common.version_ok("22.0.0"))

    def test_below_minimum(self) -> None:
        self.assertFalse(hook_common.version_ok("18.0.0"))

    def test_prerelease_suffix_handled(self) -> None:
        self.assertTrue(hook_common.version_ok("20.19.0-rc1"))

    def test_prerelease_below_minimum(self) -> None:
        self.assertFalse(hook_common.version_ok("18.0.0-beta1"))

    def test_garbage_input_returns_false(self) -> None:
        self.assertFalse(hook_common.version_ok("not-a-version"))

    def test_empty_string_returns_false(self) -> None:
        self.assertFalse(hook_common.version_ok(""))


class ExtractJsonBlobTests(unittest.TestCase):
    def test_clean_json(self) -> None:
        result = hook_common.extract_json_blob('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_json_with_leading_text(self) -> None:
        result = hook_common.extract_json_blob('some output\n{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_json_array(self) -> None:
        result = hook_common.extract_json_blob('[1, 2, 3]')
        self.assertEqual(result, [1, 2, 3])

    def test_no_json_returns_none(self) -> None:
        result = hook_common.extract_json_blob("just plain text")
        self.assertIsNone(result)

    def test_empty_string_returns_none(self) -> None:
        result = hook_common.extract_json_blob("")
        self.assertIsNone(result)


class IsApplyReadyTests(unittest.TestCase):
    def test_all_artifacts_done(self) -> None:
        status = {
            "applyRequires": ["tasks", "spec"],
            "artifacts": [
                {"id": "tasks", "status": "done"},
                {"id": "spec", "status": "done"},
            ],
        }
        self.assertTrue(hook_common.is_apply_ready(status))

    def test_missing_artifact(self) -> None:
        status = {
            "applyRequires": ["tasks", "spec"],
            "artifacts": [{"id": "tasks", "status": "done"}],
        }
        self.assertFalse(hook_common.is_apply_ready(status))

    def test_artifact_not_done(self) -> None:
        status = {
            "applyRequires": ["tasks"],
            "artifacts": [{"id": "tasks", "status": "ready"}],
        }
        self.assertFalse(hook_common.is_apply_ready(status))

    def test_none_status_returns_false(self) -> None:
        self.assertFalse(hook_common.is_apply_ready(None))

    def test_empty_apply_requires_returns_false(self) -> None:
        status = {"applyRequires": [], "artifacts": []}
        self.assertFalse(hook_common.is_apply_ready(status))


if __name__ == "__main__":
    unittest.main()
