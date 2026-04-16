from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GoCLITests(unittest.TestCase):
    def test_install_requires_force_to_overwrite_modified_managed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo = Path(tempdir) / "repo"
            repo.mkdir()

            self.init_repo(repo)

            first = self.run_cli(["install", "--skip-codex-user-config", str(repo)])
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

            managed_file = repo / ".claude" / "hooks" / "openspec_context.py"
            managed_file.write_text("# locally modified\n")

            second = self.run_cli(["install", "--skip-codex-user-config", str(repo)])
            self.assertNotEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("--force", second.stdout + second.stderr)

            third = self.run_cli(["install", "--force", "--skip-codex-user-config", str(repo)])
            self.assertEqual(third.returncode, 0, third.stdout + third.stderr)

    def test_skip_codex_user_config_passes_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo = Path(tempdir) / "repo"
            fake_home = Path(tempdir) / "home"
            repo.mkdir()
            fake_home.mkdir()
            env = {**os.environ, "HOME": str(fake_home)}

            self.init_repo(repo, env=env)

            result = self.run_cli(
                ["install", "--skip-codex-user-config", str(repo)],
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((fake_home / ".codex" / "config.toml").exists())

            doctor = self.run_cli(["doctor", str(repo)], env=env)
            self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
            self.assertIn("healthcheck", doctor.stdout + doctor.stderr)

    def test_version_matches_version_file(self) -> None:
        version = (ROOT / "VERSION").read_text().strip()
        result = self.run_cli(["version"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), version)

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

    @staticmethod
    def run_cli(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        go_cache = Path(tempfile.gettempdir()) / "openspec-auto-gocache"
        go_tmp = Path(tempfile.gettempdir()) / "openspec-auto-gotmp"
        go_cache.mkdir(parents=True, exist_ok=True)
        go_tmp.mkdir(parents=True, exist_ok=True)
        run_env = {
            **os.environ,
            "GOCACHE": str(go_cache),
            "GOTMPDIR": str(go_tmp),
        }
        if env is not None:
            run_env.update(env)
        return subprocess.run(
            ["go", "run", "./cmd/openspec-auto", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=run_env,
        )


if __name__ == "__main__":
    unittest.main()
