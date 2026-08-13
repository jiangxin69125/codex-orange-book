from pathlib import Path
import unittest


README = Path(__file__).resolve().parents[1] / "README.md"


class ReadmeCommandTests(unittest.TestCase):
    def test_cli_startup_rows_use_real_executable_name(self):
        readme = README.read_text(encoding="utf-8")

        self.assertIn("| `codex` | 启动 Codex CLI |", readme)
        self.assertNotIn("| Codex | 启动 Codex CLI |", readme)


if __name__ == "__main__":
    unittest.main()
