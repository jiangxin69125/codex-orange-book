import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


class ReadmeExecPermissionsTest(unittest.TestCase):
    def test_exec_section_warns_that_human_approval_is_disabled(self) -> None:
        text = README.read_text(encoding="utf-8")
        exec_section = text.split("###### 非交互式任务命令", 1)[1].split(
            "###### 会话管理命令", 1
        )[0]

        self.assertIn("`codex exec` 不会等待人工批准", exec_section)
        self.assertIn("即使普通交互会话设置了 `on-request`", exec_section)
        self.assertIn(
            'codex exec --sandbox read-only "请检查当前项目有没有明显问题"',
            exec_section,
        )
        self.assertNotIn(
            '\ncodex exec "请检查当前项目有没有明显问题"\n',
            exec_section,
        )


if __name__ == "__main__":
    unittest.main()
