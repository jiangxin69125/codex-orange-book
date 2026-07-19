#!/usr/bin/env python3
"""Regression tests for the PDF build pipeline."""

import re
import unittest

from tools.build_pdf import render_readme


class RenderReadmeTests(unittest.TestCase):
    def test_table_of_contents_links_have_heading_targets(self) -> None:
        html = render_readme()
        toc_links = re.findall(r'href="#([^"]+)"', html)
        heading_ids = set(re.findall(r'<h[1-6] id="([^"]+)"', html))

        self.assertGreater(len(toc_links), 0)
        self.assertEqual([], [link for link in toc_links if link not in heading_ids])


if __name__ == "__main__":
    unittest.main()
