import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


class ReadmePermissionGuidanceTest(unittest.TestCase):
    def test_beginner_guidance_requires_manual_approval(self) -> None:
        text = README.read_text(encoding="utf-8")
        permission_section = text.split("###### 三大权限", 1)[1].split(
            "###### 一句话总结", 1
        )[0]

        self.assertIn("**优先选择“请求批准”**", permission_section)
        self.assertIn(
            "不能保证每次越界、联网或高风险操作都会停下来", permission_section
        )
        self.assertNotIn("**请求批准或自动审批类选项**", permission_section)


if __name__ == "__main__":
    unittest.main()
