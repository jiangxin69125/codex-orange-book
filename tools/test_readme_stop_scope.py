#!/usr/bin/env python3
"""Regression tests for the destructive scope of the /stop command."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


class ReadmeStopScopeTests(unittest.TestCase):
    def test_stop_guidance_warns_that_every_background_terminal_is_stopped(self) -> None:
        text = README.read_text(encoding="utf-8")
        section_start = text.index("###### 终端和后台任务相关")
        section_end = text.index("###### 界面与快捷键相关", section_start)
        guidance = text[section_start:section_end]

        required_guidance = (
            "停止所有后台终端任务",
            "`/stop` 不能选择单个任务",
            "数据库迁移、文件写入、部署",
            "不要使用 `/stop`",
            "只终止那一个命令",
        )
        for warning in required_guidance:
            with self.subTest(warning=warning):
                self.assertIn(warning, guidance)

        misleading_guidance = (
            "| /stop | 停止后台终端任务 |",
            "→ 用 /stop\n",
            "用 /stop 停止后台任务",
            "| 9 | /stop | 停止卡住的命令 |",
        )
        for warning in misleading_guidance:
            with self.subTest(warning=warning):
                self.assertNotIn(warning, text)


if __name__ == "__main__":
    unittest.main()
