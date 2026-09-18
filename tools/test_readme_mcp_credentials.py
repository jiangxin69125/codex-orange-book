import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


class ReadmeMcpCredentialsTest(unittest.TestCase):
    def test_mcp_guidance_does_not_store_secrets_in_fixed_env_values(self) -> None:
        text = README.read_text(encoding="utf-8")
        mcp_section = text.split("##### 添加 MCP 时通常需要填什么", 1)[1].split(
            "##### 添加 MCP 后怎么使用", 1
        )[0]
        config_section = text.split("##### MCP 配置文件在哪里", 1)[1].split(
            "##### 添加远程 MCP", 1
        )[0]

        self.assertNotIn("Env | 环境变量 | 放 token", mcp_section)
        self.assertIn("不要放 token、API Key 或密码", mcp_section)
        self.assertIn("环境变量传递", mcp_section)
        self.assertIn("只填写变量名", mcp_section)
        self.assertIn("明文保存", mcp_section)
        self.assertIn("不要公开、上传或提交这个文件", config_section)
        self.assertIn("轮换对应凭证", config_section)


if __name__ == "__main__":
    unittest.main()
