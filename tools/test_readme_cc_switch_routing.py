import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


class ReadmeCcSwitchRoutingTest(unittest.TestCase):
    def test_only_codex_is_routed_for_deepseek_example(self) -> None:
        text = README.read_text(encoding="utf-8")
        appendix = text.split("### 附录 A：第三方模型接入", 1)[1]

        self.assertNotIn("将路由全部打开", appendix)
        self.assertIn("卡片带有「需要路由」标记时才开启", appendix)
        self.assertIn("**只打开 `Codex`**", appendix)
        self.assertIn("不要为了这个示例打开 `Claude` 或 `Gemini`", appendix)
        self.assertIn("会改写它们的实时 API 地址和认证配置", appendix)


if __name__ == "__main__":
    unittest.main()
