from __future__ import annotations

import subprocess
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pyc", ".iml", ".DS_Store"}
SKIP_PARTS = {".git", ".idea", "__pycache__"}
LEAK_PATTERN = re.compile(r"/Users/[^/\s]+")


class RepositoryHygieneTests(unittest.TestCase):
    def test_tracked_text_files_do_not_contain_local_absolute_paths(self) -> None:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )

        leaked: list[str] = []
        for line in result.stdout.splitlines():
            path = ROOT / line
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            if path.suffix in SKIP_SUFFIXES:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if LEAK_PATTERN.search(content):
                leaked.append(line)

        self.assertEqual(leaked, [], f"found local absolute paths in: {leaked}")


if __name__ == "__main__":
    unittest.main()
