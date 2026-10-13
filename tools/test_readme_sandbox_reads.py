import unittest
from pathlib import Path


README = Path(__file__).resolve().parent.parent / "README.md"


class ReadmeSandboxReadBoundaryTests(unittest.TestCase):
    def test_project_sandbox_is_not_described_as_a_read_boundary(self) -> None:
        text = README.read_text(encoding="utf-8")
        sandbox_section = text.split("###### 沙盒（Sandbox）", 1)[1].split(
            "###### Model 模型选择",
            1,
        )[0]
        troubleshooting_section = text.split("##### 权限和沙盒类问题", 1)[1].split(
            "##### 命令运行类问题",
            1,
        )[0]

        self.assertIn("默认仍可读取本机其他目录", sandbox_section)
        self.assertIn("读取项目外文件通常不会单独弹出批准提示", sandbox_section)
        self.assertIn("独立系统账号、容器或虚拟机", sandbox_section)
        self.assertNotIn(
            "Codex 正常只能在这个项目文件夹范围内工作",
            sandbox_section,
        )
        self.assertNotIn(
            "Codex 不能读取项目外文件",
            troubleshooting_section,
        )
        self.assertIn(
            "不代表项目外文件不可读",
            troubleshooting_section,
        )


if __name__ == "__main__":
    unittest.main()
