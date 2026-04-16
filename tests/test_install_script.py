from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = ROOT / "install.sh"


class InstallScriptTests(unittest.TestCase):
    def test_install_requires_force_to_overwrite_modified_managed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo = Path(tempdir) / "repo"
            repo.mkdir()

            self.run_command(["git", "init"], cwd=repo)
            self.run_command(["git", "branch", "-M", "main"], cwd=repo)
            self.run_command(["git", "config", "user.name", "Test User"], cwd=repo)
            self.run_command(["git", "config", "user.email", "test@example.com"], cwd=repo)

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

            self.run_command(["git", "init"], cwd=repo)
            self.run_command(["git", "branch", "-M", "main"], cwd=repo)
            self.run_command(["git", "config", "user.name", "Test User"], cwd=repo)
            self.run_command(["git", "config", "user.email", "test@example.com"], cwd=repo)

            result = subprocess.run(
                [str(INSTALL_SCRIPT), "--skip-codex-user-config", str(repo)],
                text=True,
                capture_output=True,
                check=False,
                env={**__import__("os").environ, "HOME": str(fake_home)},
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            # healthcheck should also pass (warn, not fail)
            healthcheck = repo / "tools" / "openspec" / "healthcheck.sh"
            hc_result = subprocess.run(
                [str(healthcheck), str(repo)],
                text=True,
                capture_output=True,
                check=False,
                env={**__import__("os").environ, "HOME": str(fake_home)},
            )
            self.assertEqual(hc_result.returncode, 0, hc_result.stdout + hc_result.stderr)
            # Should contain a warning about codex_hooks
            combined = hc_result.stdout + hc_result.stderr
            self.assertIn("warn", combined.lower())

    @staticmethod
    def run_command(args: list[str], cwd: Path) -> None:
        subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
