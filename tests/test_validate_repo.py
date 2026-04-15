from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATE_REPO = ROOT / "templates" / "repo" / "tools" / "openspec" / "validate_repo.py"


class ValidateRepoCliTests(unittest.TestCase):
    def test_ci_uses_base_ref_diff_even_when_worktree_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo = Path(tempdir) / "repo"
            repo.mkdir()

            self.run_command(["git", "init"], cwd=repo)
            self.run_command(["git", "branch", "-M", "main"], cwd=repo)
            self.run_command(["git", "config", "user.name", "Test User"], cwd=repo)
            self.run_command(["git", "config", "user.email", "test@example.com"], cwd=repo)

            (repo / "README.md").write_text("# demo\n")
            self.run_command(["git", "add", "README.md"], cwd=repo)
            self.run_command(["git", "commit", "-m", "initial"], cwd=repo)

            self.run_command(["git", "checkout", "-b", "feature/test"], cwd=repo)
            (repo / "main.go").write_text("package main\n")
            self.run_command(["git", "add", "main.go"], cwd=repo)
            self.run_command(["git", "commit", "-m", "add code"], cwd=repo)

            result = subprocess.run(
                [
                    "python3",
                    str(VALIDATE_REPO),
                    "--repo",
                    str(repo),
                    "--ci",
                    "--base-ref",
                    "main",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("main.go", payload["changedOutsideOpenSpec"])
            self.assertFalse(payload["ok"])

    @staticmethod
    def run_command(args: list[str], cwd: Path) -> None:
        subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
