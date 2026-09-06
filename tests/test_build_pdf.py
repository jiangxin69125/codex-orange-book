import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import build_pdf


REFORMATTED_COVER = """<!DOCTYPE html>
<html>
<head>
<style>
  @page
  {
    size: A4;
    margin: 0;
  }

  *
  {
    margin : 0 ;
    padding: 0;
    box-sizing : border-box ;
  }

  html ,
  body
  {
    width: 210mm;
    height: 297mm;
    overflow: hidden;
  }
</style>
</head>
<body><div class="cover">Cover</div></body>
</html>
"""


class ExtractCoverTests(unittest.TestCase):
    def test_rewrites_harmlessly_reformatted_required_css(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cover = Path(directory) / "cover.html"
            cover.write_text(REFORMATTED_COVER, encoding="utf-8")

            with mock.patch.object(build_pdf, "COVER", cover):
                style, body = build_pdf.extract_cover()

        self.assertNotIn("@page", style)
        self.assertIn(".cover, .cover * {", style)
        self.assertFalse(re.search(r"(?m)^[ \t]*\*\s*\{", style))
        self.assertFalse(re.search(r"html\s*,\s*body\s*\{", style))
        self.assertIn(".cover {", style)
        self.assertIn('<div class="cover">Cover</div>', body)

    def test_rejects_missing_or_duplicated_required_css(self) -> None:
        invalid_covers = {
            "missing reset": REFORMATTED_COVER.replace(
                """  *
  {
    margin : 0 ;
    padding: 0;
    box-sizing : border-box ;
  }

""",
                "",
            ),
            "missing document selector": REFORMATTED_COVER.replace(
                "  html ,\n  body\n  {",
                "  .cover {",
            ),
            "duplicated page rule": REFORMATTED_COVER.replace(
                "  @page\n",
                "  @page { size: A4; margin: 0; }\n  @page\n",
            ),
        }

        for name, raw_cover in invalid_covers.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                cover = Path(directory) / "cover.html"
                cover.write_text(raw_cover, encoding="utf-8")

                with mock.patch.object(build_pdf, "COVER", cover):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "Cover CSS rewrite failed",
                    ):
                        build_pdf.extract_cover()

    def test_build_failure_preserves_existing_pdf_and_skips_export(self) -> None:
        invalid_cover = REFORMATTED_COVER.replace(
            "  html ,\n  body\n  {",
            "  .cover {",
        )
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            cover = directory_path / "cover.html"
            book_html = directory_path / "book.html"
            output_pdf = directory_path / "book.pdf"
            cover.write_text(invalid_cover, encoding="utf-8")
            output_pdf.write_bytes(b"existing tracked PDF")

            with (
                mock.patch.object(build_pdf, "COVER", cover),
                mock.patch.object(build_pdf, "BOOK_HTML", book_html),
                mock.patch.object(build_pdf, "OUTPUT_PDF", output_pdf),
                mock.patch.object(build_pdf, "render_readme", return_value="<p>book</p>"),
                mock.patch.object(build_pdf.subprocess, "run") as run,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "html/body selector \\(0 matches\\)",
                ):
                    build_pdf.build()

            self.assertFalse(book_html.exists())
            self.assertEqual(output_pdf.read_bytes(), b"existing tracked PDF")
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
