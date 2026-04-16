from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = ROOT / "install.sh"
UNINSTALL_SCRIPT = ROOT / "uninstall.sh"


class InstallScriptTests(unittest.TestCase):
    def test_install_requires_force_to_overwrite_modified_managed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo = Path(tempdir) / "repo"
            repo.mkdir()

            self.init_repo(repo)

            first = subprocess.run(
                [str(INSTALL_SCRIPT), "--skip-codex-user-config", str(repo)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

            managed_file = repo / ".claude" / "hooks" / "openspec_context.py"
            managed_file.write_text("# locally modified\n")

            second = subprocess.run(
                [str(INSTALL_SCRIPT), "--skip-codex-user-config", str(repo)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("--force", second.stdout + second.stderr)

            third = subprocess.run(
                [str(INSTALL_SCRIPT), "--force", "--skip-codex-user-config", str(repo)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(third.returncode, 0, third.stdout + third.stderr)

    def test_skip_codex_user_config_passes_with_warning(self) -> None:
        """install --skip-codex-user-config should succeed even when ~/.codex/config.toml is absent."""
        with tempfile.TemporaryDirectory() as tempdir:
            repo = Path(tempdir) / "repo"
            fake_home = Path(tempdir) / "home"
            repo.mkdir()
            fake_home.mkdir()
            env = {**os.environ, "HOME": str(fake_home)}

            self.init_repo(repo, env=env)

            result = subprocess.run(
                [str(INSTALL_SCRIPT), "--skip-codex-user-config", str(repo)],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((fake_home / ".codex" / "config.toml").exists())

            # healthcheck should also pass (warn, not fail)
            healthcheck = repo / "tools" / "openspec" / "healthcheck.sh"
            hc_result = subprocess.run(
                [str(healthcheck), str(repo)],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )
            self.assertEqual(hc_result.returncode, 0, hc_result.stdout + hc_result.stderr)
            # Should contain a warning about codex_hooks
            combined = hc_result.stdout + hc_result.stderr
            self.assertIn("warn", combined.lower())

    def test_healthcheck_fails_when_codex_guard_hook_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo = Path(tempdir) / "repo"
            fake_home = Path(tempdir) / "home"
            repo.mkdir()
            fake_home.mkdir()
            env = {**os.environ, "HOME": str(fake_home)}

            self.init_repo(repo, env=env)

            install = subprocess.run(
                [str(INSTALL_SCRIPT), str(repo)],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )
            self.assertEqual(install.returncode, 0, install.stdout + install.stderr)

            guard_hook = repo / ".codex" / "hooks" / "openspec_guard.py"
            guard_hook.unlink()

            healthcheck = subprocess.run(
                [str(repo / "tools" / "openspec" / "healthcheck.sh"), str(repo)],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )
            self.assertEqual(healthcheck.returncode, 1, healthcheck.stdout + healthcheck.stderr)
            self.assertIn(".codex/hooks/openspec_guard.py", healthcheck.stderr)

            uninstall = subprocess.run(
                [str(UNINSTALL_SCRIPT), str(repo)],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )
            self.assertEqual(uninstall.returncode, 0, uninstall.stdout + uninstall.stderr)
            self.assertFalse((repo / ".openspec-auto").exists())

    @staticmethod
    def run_command(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
        subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True, env=env)

    @classmethod
    def init_repo(cls, repo: Path, env: dict[str, str] | None = None) -> None:
        cls.run_command(["git", "init"], cwd=repo, env=env)
        cls.run_command(["git", "branch", "-M", "main"], cwd=repo, env=env)
        cls.run_command(["git", "config", "user.name", "Test User"], cwd=repo, env=env)
        cls.run_command(["git", "config", "user.email", "test@example.com"], cwd=repo, env=env)
        (repo / "README.md").write_text("# demo\n")
        cls.run_command(["git", "add", "README.md"], cwd=repo, env=env)
        cls.run_command(["git", "commit", "-m", "initial"], cwd=repo, env=env)


if __name__ == "__main__":
    unittest.main()
