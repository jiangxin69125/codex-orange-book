#!/usr/bin/env python3
"""Regression tests for security-sensitive README commands."""

import re
import unittest
from pathlib import Path


README = Path(__file__).resolve().parent.parent / "README.md"


class ReadmeSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = README.read_text(encoding="utf-8")

    def test_does_not_recommend_staging_the_entire_worktree(self) -> None:
        unsafe_command = re.compile(r"(?m)^\s*git add \.\s*$")

        self.assertNotRegex(self.text, unsafe_command)

    def test_git_setup_ignores_local_environment_files(self) -> None:
        self.assertIn(".env\n.env.*\n!.env.example", self.text)


if __name__ == "__main__":
    unittest.main()
