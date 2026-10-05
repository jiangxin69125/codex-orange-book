import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


class ReadmeSearchSafetyTest(unittest.TestCase):
    def test_search_documents_unapproved_network_egress(self) -> None:
        text = README.read_text(encoding="utf-8")
        search_section = text.split("###### 启动时直接发任务", 1)[1].split(
            "###### 模型、权限、沙盒相关命令", 1
        )[0]

        self.assertIn("搜索调用**不会逐次请求你的批准**", search_section)
        self.assertIn("`workspace-write` 沙盒和 `on-request` 审批", search_section)
        self.assertIn("密钥、客户数据、私有代码或内部地址", search_section)
        self.assertIn("脱敏后的测试副本", search_section)


if __name__ == "__main__":
    unittest.main()
