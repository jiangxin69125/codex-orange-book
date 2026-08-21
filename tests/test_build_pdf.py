import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import build_pdf


def pdf_path(command: list[str]) -> Path:
    argument = next(
        item for item in command if item.startswith("--print-to-pdf=")
    )
    return Path(argument.split("=", 1)[1])


class ExportPdfTest(unittest.TestCase):
    def test_failed_export_preserves_existing_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_html = root / "book.html"
            output_pdf = root / "book.pdf"
            input_html.write_text("<html></html>", encoding="utf-8")
            output_pdf.write_bytes(b"known-good-pdf")

            def fail_after_partial_write(command: list[str], **_: object) -> None:
                pdf_path(command).write_bytes(b"partial")
                raise subprocess.CalledProcessError(1, command)

            with mock.patch.object(
                build_pdf.subprocess,
                "run",
                side_effect=fail_after_partial_write,
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    build_pdf.export_pdf(input_html, output_pdf)

            self.assertEqual(output_pdf.read_bytes(), b"known-good-pdf")
            self.assertEqual(list(root.glob(".build-pdf-*")), [])

    def test_successful_export_replaces_existing_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_html = root / "book.html"
            output_pdf = root / "book.pdf"
            input_html.write_text("<html></html>", encoding="utf-8")
            output_pdf.write_bytes(b"old-pdf")

            def write_complete_pdf(command: list[str], **_: object) -> None:
                pdf_path(command).write_bytes(b"complete-pdf")

            with mock.patch.object(
                build_pdf.subprocess,
                "run",
                side_effect=write_complete_pdf,
            ):
                build_pdf.export_pdf(input_html, output_pdf)

            self.assertEqual(output_pdf.read_bytes(), b"complete-pdf")
            self.assertEqual(list(root.glob(".build-pdf-*")), [])


if __name__ == "__main__":
    unittest.main()
