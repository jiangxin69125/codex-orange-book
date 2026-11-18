import re
import unittest

from tools import build_pdf


class PrintStylesTests(unittest.TestCase):
    def test_fenced_code_can_continue_across_pages(self) -> None:
        pre_rule = re.search(
            r"\.content pre\s*\{(?P<declarations>.*?)\}",
            build_pdf.BOOK_CSS,
            re.DOTALL,
        )

        self.assertIsNotNone(pre_rule)
        declarations = pre_rule.group("declarations")
        self.assertIn("overflow: visible", declarations)
        self.assertIn("break-inside: auto", declarations)
        self.assertNotIn("overflow: hidden", declarations)
        self.assertNotIn("break-inside: avoid", declarations)


if __name__ == "__main__":
    unittest.main()
