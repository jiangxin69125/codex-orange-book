from pathlib import Path
import unittest


README = Path(__file__).resolve().parents[1] / "README.md"


class ReadmeCommandTests(unittest.TestCase):
    def test_cli_startup_rows_use_real_executable_name(self):
        startup_rows = [
            line.split("|")[1:-1]
            for line in README.read_text(encoding="utf-8").splitlines()
            if line.startswith("|") and "启动 Codex CLI" in line
        ]

        self.assertEqual(3, len(startup_rows))
        for cells in startup_rows:
            command = cells[-2].strip()
            self.assertEqual("`codex`", command)


if __name__ == "__main__":
    unittest.main()
