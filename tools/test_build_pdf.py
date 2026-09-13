from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import build_pdf


class BuildPdfTests(unittest.TestCase):
    def test_missing_local_images_prevent_html_write_and_chrome_launch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            book_html = root / "book.html"
            rendered_html = """
<img src="assets/missing-one.png">
<img src="assets/missing%20two.png?size=large#preview">
<img src="https://example.com/remote.png">
"""

            with (
                patch.object(build_pdf, "ROOT", root),
                patch.object(build_pdf, "BOOK_HTML", book_html),
                patch.object(build_pdf, "extract_cover", return_value=("", "")),
                patch.object(build_pdf, "render_readme", return_value=rendered_html),
                patch.object(build_pdf.subprocess, "run") as chrome_run,
            ):
                with self.assertRaises(FileNotFoundError) as raised:
                    build_pdf.build()

            message = str(raised.exception)
            self.assertIn("assets/missing-one.png", message)
            self.assertIn(str(root / "assets/missing-one.png"), message)
            self.assertIn("assets/missing%20two.png?size=large#preview", message)
            self.assertIn(str(root / "assets/missing two.png"), message)
            self.assertNotIn("remote.png", message)
            self.assertFalse(book_html.exists())
            chrome_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
