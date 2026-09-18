import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import build_pdf


class BuildPdfSecurityTests(unittest.TestCase):
    def test_current_readme_and_cover_use_only_safe_html(self) -> None:
        cover_style, cover_body = build_pdf.extract_cover()

        build_pdf.validate_cover_style(cover_style)
        build_pdf.validate_html_fragment(cover_body, "cover.html")
        build_pdf.validate_html_fragment(build_pdf.render_readme(), "README.md")

    def test_active_html_and_unsafe_attributes_are_rejected(self) -> None:
        unsafe_fragments = (
            '<iframe src=".env"></iframe>',
            "<script>while(true){}</script>",
            "</iframe>",
            '<meta http-equiv="refresh" content="0; url=.env">',
            '<p onclick="fetch(\'https://example.com\')">unsafe</p>',
            '<a href="file:///etc/passwd">local file</a>',
        )

        for fragment in unsafe_fragments:
            with self.subTest(fragment=fragment):
                with self.assertRaises(ValueError):
                    build_pdf.validate_html_fragment(fragment, "test")

    def test_build_rejects_active_html_before_writing_or_launching_chrome(
        self,
    ) -> None:
        unsafe_fragments = {
            "readme_iframe": (
                "<div>cover</div>",
                '<iframe src=".env"></iframe>',
            ),
            "readme_script": (
                "<div>cover</div>",
                "<script>while(true){}</script>",
            ),
            "cover_iframe": (
                '<iframe src=".env"></iframe>',
                "<p>book</p>",
            ),
            "cover_script": (
                "<script>while(true){}</script>",
                "<p>book</p>",
            ),
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, (cover_body, content_html) in unsafe_fragments.items():
                with self.subTest(name=name):
                    book_html = root / f"{name}.html"
                    with (
                        mock.patch.object(build_pdf, "ROOT", root),
                        mock.patch.object(build_pdf, "ASSETS", root / "assets"),
                        mock.patch.object(build_pdf, "BOOK_HTML", book_html),
                        mock.patch.object(
                            build_pdf,
                            "extract_cover",
                            return_value=("", cover_body),
                        ),
                        mock.patch.object(
                            build_pdf,
                            "render_readme",
                            return_value=content_html,
                        ),
                        mock.patch.object(
                            build_pdf.subprocess,
                            "run",
                        ) as chrome_run,
                    ):
                        with self.assertRaisesRegex(
                            ValueError,
                            "unsupported HTML tag",
                        ):
                            build_pdf.build()

                    self.assertFalse(book_html.exists())
                    chrome_run.assert_not_called()

    def test_images_must_exist_beneath_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "safe.png").write_bytes(b"image")
            (assets / "untracked.png").write_bytes(b"local-only")
            (root / "secret.png").write_bytes(b"secret")

            with (
                mock.patch.object(build_pdf, "ROOT", root),
                mock.patch.object(build_pdf, "ASSETS", assets),
                mock.patch.object(
                    build_pdf,
                    "checked_in_asset_paths",
                    return_value={"assets/safe.png"},
                ),
            ):
                build_pdf.validate_html_fragment(
                    '<img src="assets/safe.png" alt="safe">',
                    "test",
                )
                with self.assertRaisesRegex(ValueError, "relative assets"):
                    build_pdf.validate_html_fragment(
                        '<img src="secret.png" alt="unsafe">',
                        "test",
                    )
                with self.assertRaisesRegex(ValueError, "not checked in"):
                    build_pdf.validate_html_fragment(
                        '<img src="assets/untracked.png" alt="unsafe">',
                        "test",
                    )

    def test_image_symlinks_cannot_escape_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            local_only = assets / "local-only.png"
            local_only.write_bytes(b"local-only")
            (assets / "linked.png").symlink_to(local_only)

            with (
                mock.patch.object(build_pdf, "ROOT", root),
                mock.patch.object(build_pdf, "ASSETS", assets),
                mock.patch.object(
                    build_pdf,
                    "checked_in_asset_paths",
                    return_value={"assets/linked.png"},
                ),
            ):
                with self.assertRaisesRegex(ValueError, "cannot contain symlinks"):
                    build_pdf.validate_html_fragment(
                        '<img src="assets/linked.png" alt="unsafe">',
                        "test",
                    )

    def test_assets_directory_cannot_be_a_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            outside.mkdir()
            (outside / "local-only.png").write_bytes(b"local-only")
            assets = root / "assets"
            assets.symlink_to(outside, target_is_directory=True)

            with (
                mock.patch.object(build_pdf, "ROOT", root),
                mock.patch.object(build_pdf, "ASSETS", assets),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "assets/ directory cannot be a symlink",
                ):
                    build_pdf.validate_html_fragment(
                        '<img src="assets/local-only.png" alt="unsafe">',
                        "test",
                    )

    def test_cover_css_cannot_load_resources(self) -> None:
        unsafe_styles = (
            '@import "file:///etc/passwd";',
            "body { background: url(https://example.com/tracker.png); }",
            r'body { background: \75rl("file:///etc/passwd"); }',
            'body { background: u/**/rl("file:///etc/passwd"); }',
            r'@\69mport "file:///etc/passwd";',
            'body { background: image-set("file:///etc/passwd" 1x); }',
        )

        for style in unsafe_styles:
            with self.subTest(style=style):
                with self.assertRaises(ValueError):
                    build_pdf.validate_cover_style(style)

    def test_build_enforces_csp_and_chrome_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            book_html = root / "book.html"
            output_pdf = root / "book.pdf"

            def write_pdf(_command: list[str], **_kwargs: object) -> None:
                output_pdf.write_bytes(b"pdf")

            with (
                mock.patch.object(build_pdf, "ROOT", root),
                mock.patch.object(build_pdf, "ASSETS", root / "assets"),
                mock.patch.object(build_pdf, "BOOK_HTML", book_html),
                mock.patch.object(build_pdf, "OUTPUT_PDF", output_pdf),
                mock.patch.object(
                    build_pdf,
                    "extract_cover",
                    return_value=("", "<div>cover</div>"),
                ),
                mock.patch.object(
                    build_pdf,
                    "render_readme",
                    return_value="<p>book</p>",
                ),
                mock.patch.object(
                    build_pdf.subprocess,
                    "run",
                    side_effect=write_pdf,
                ) as chrome_run,
            ):
                build_pdf.build()

            document = book_html.read_text(encoding="utf-8")
            self.assertIn("Content-Security-Policy", document)
            self.assertIn("script-src 'none'", document)
            self.assertIn("frame-src 'none'", document)
            self.assertEqual(300, chrome_run.call_args.kwargs["timeout"])


if __name__ == "__main__":
    unittest.main()
