#!/usr/bin/env python3
"""Regression tests for safety guidance around the public static demo."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
DEMO_URL = "https://vink567.github.io/Pet-treats/"


class ReadmeDemoSafetyTests(unittest.TestCase):
    def test_public_demo_is_preceded_by_explicit_data_safety_warning(self) -> None:
        text = README.read_text(encoding="utf-8")
        demo_position = text.index(DEMO_URL)
        preceding_guidance = text[max(0, demo_position - 700) : demo_position]

        required_warnings = (
            "只用于静态前端演示",
            "没有真正的服务端认证、密码加密或后台权限控制",
            "不要输入真实邮箱",
            "在其他网站使用过的密码",
            "真实电话或地址",
            "不要把它当作真实商店上线",
        )
        for warning in required_warnings:
            with self.subTest(warning=warning):
                self.assertIn(warning, preceding_guidance)


if __name__ == "__main__":
    unittest.main()
