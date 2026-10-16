import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


class ReadmeCliRequiredArgumentsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = README.read_text(encoding="utf-8")

    def test_archive_commands_name_the_required_session(self) -> None:
        self.assertIn("`codex archive 会话ID或名称`", self.text)
        self.assertIn("`codex unarchive 会话ID或名称`", self.text)
        self.assertNotIn("| `codex archive` |", self.text)
        self.assertNotIn("| `codex unarchive` |", self.text)

    def test_current_session_workflow_uses_slash_archive(self) -> None:
        self.assertIn("| 9 | `/archive` 或 `/quit` |", self.text)

    def test_sandbox_command_names_the_required_profile(self) -> None:
        self.assertIn(
            "`codex sandbox --permission-profile 配置档名称 "
            "--cd 项目目录 -- 命令`",
            self.text,
        )
        self.assertNotIn("`codex sandbox --cd 项目目录 -- 命令`", self.text)


if __name__ == "__main__":
    unittest.main()
