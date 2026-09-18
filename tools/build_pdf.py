#!/usr/bin/env python3
"""把 README.md + cover.html 合并渲染成单个 PDF（Chrome headless 导出）。

流程：
1. 读取 cover.html，取出其 <style> 与封面 <div class="cover">，做多页上下文适配后嵌入；
2. 用 python-markdown 把 README 正文转成 HTML（支持表格、围栏代码、原始 HTML 图片块）；
3. 套上整本书的打印 CSS（A4、页边距、表格/代码/图片样式），封面用命名页占满一整页；
4. 输出 book.html 到仓库根目录（让 assets/ 相对路径能被解析），再调用 Chrome --print-to-pdf。
"""

from __future__ import annotations

import os
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

import markdown

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
COVER = ROOT / "cover.html"
BOOK_HTML = ROOT / "book.html"
OUTPUT_PDF = ROOT / "Codex橙皮书.pdf"
ASSETS = ROOT / "assets"

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_TIMEOUT_SECONDS = 300
GIT_TIMEOUT_SECONDS = 10

ALLOWED_HTML_ATTRIBUTES = {
    "a": {"href"},
    "blockquote": set(),
    "br": set(),
    "code": {"class"},
    "div": {"class"},
    "em": set(),
    "footer": {"class"},
    "h1": {"class"},
    "h2": {"class"},
    "h3": {"class"},
    "h4": {"class"},
    "h5": {"class"},
    "h6": {"class"},
    "header": {"class"},
    "hr": set(),
    "img": {"alt", "height", "src", "width"},
    "li": set(),
    "nav": {"class"},
    "ol": {"start"},
    "p": {"align", "class"},
    "pre": set(),
    "section": {"class"},
    "span": {"class"},
    "strong": set(),
    "table": set(),
    "tbody": set(),
    "td": set(),
    "th": set(),
    "thead": set(),
    "tr": set(),
    "ul": set(),
}

CONTENT_SECURITY_POLICY = (
    "default-src 'none'; "
    "img-src file: data:; "
    "style-src 'unsafe-inline'; "
    "font-src 'none'; "
    "script-src 'none'; "
    "object-src 'none'; "
    "frame-src 'none'; "
    "media-src 'none'; "
    "connect-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)

CSS_COMMENTS = re.compile(r"/\*.*?\*/", flags=re.S)
CSS_RESOURCE_CONSTRUCT = re.compile(
    r"(?:@import\b|(?<![\w-])(?:url|src|image|cross-fade|(?:-[a-z]+-)?image-set)\s*\()",
    flags=re.I,
)


def checked_in_asset_paths() -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--", "assets/"],
        check=True,
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    return {
        os.fsdecode(path)
        for path in result.stdout.split(b"\0")
        if path
    }


class SafeHtmlValidator(HTMLParser):
    """Reject active HTML and local resources outside the checked-in assets."""

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.checked_in_assets: set[str] | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_HTML_ATTRIBUTES:
            raise ValueError(f"{self.source} contains unsupported HTML tag <{tag}>")

        allowed_attributes = ALLOWED_HTML_ATTRIBUTES[tag]
        for name, value in attrs:
            name = name.lower()
            if name not in allowed_attributes:
                raise ValueError(
                    f"{self.source} contains unsupported attribute {name!r} on <{tag}>"
                )
            if value is None:
                raise ValueError(
                    f"{self.source} contains an empty {name!r} attribute on <{tag}>"
                )
            if tag == "img" and name == "src":
                self._validate_image_source(value)
            elif tag == "a" and name == "href":
                self._validate_link(value)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_HTML_ATTRIBUTES:
            raise ValueError(f"{self.source} contains unsupported HTML tag </{tag}>")

    def handle_decl(self, decl: str) -> None:
        raise ValueError(f"{self.source} contains unsupported declaration <!{decl}>")

    def handle_pi(self, data: str) -> None:
        raise ValueError(f"{self.source} contains unsupported processing instruction")

    def _validate_image_source(self, source: str) -> None:
        parsed = urlsplit(source)
        if parsed.scheme or parsed.netloc:
            raise ValueError(
                f"{self.source} image source must be a local assets/ path: {source}"
            )

        decoded_path = unquote(parsed.path)
        relative_path = PurePosixPath(decoded_path)
        if (
            "\\" in decoded_path
            or relative_path.is_absolute()
            or not relative_path.parts
            or relative_path.parts[0] != "assets"
            or ".." in relative_path.parts
        ):
            raise ValueError(
                f"{self.source} image source must be a relative assets/ path: {source}"
            )

        root_path = ROOT.resolve()
        requested_image_path = root_path / Path(*relative_path.parts)
        image_path = requested_image_path.resolve()
        assets_path = ASSETS.resolve()
        if assets_path != root_path / "assets":
            raise ValueError(f"{self.source} assets/ directory cannot be a symlink")
        if image_path != requested_image_path:
            raise ValueError(
                f"{self.source} image source cannot contain symlinks: {source}"
            )
        try:
            image_path.relative_to(assets_path)
        except ValueError as error:
            raise ValueError(
                f"{self.source} image source escapes assets/: {source}"
            ) from error
        if not image_path.is_file():
            raise FileNotFoundError(
                f"{self.source} image source does not exist: {source}"
            )
        if self.checked_in_assets is None:
            self.checked_in_assets = checked_in_asset_paths()
        if relative_path.as_posix() not in self.checked_in_assets:
            raise ValueError(
                f"{self.source} image source is not checked in: {source}"
            )

    def _validate_link(self, href: str) -> None:
        if any(character.isspace() for character in href):
            raise ValueError(f"{self.source} contains an invalid link: {href}")
        parsed = urlsplit(href)
        if parsed.scheme.lower() not in {"", "http", "https", "mailto"}:
            raise ValueError(
                f"{self.source} contains unsupported link scheme: {href}"
            )
        if not parsed.scheme and (parsed.netloc or parsed.path):
            raise ValueError(
                f"{self.source} contains unsupported local link: {href}"
            )


def validate_html_fragment(fragment: str, source: str) -> None:
    validator = SafeHtmlValidator(source)
    validator.feed(fragment)
    validator.close()


def validate_cover_style(style: str) -> None:
    style_without_comments = CSS_COMMENTS.sub("", style)
    if "\\" in style_without_comments:
        raise ValueError("cover CSS escapes are not allowed")
    if CSS_RESOURCE_CONSTRUCT.search(style_without_comments):
        raise ValueError("cover CSS cannot load local or remote resources")


def extract_cover() -> tuple[str, str]:
    """取出封面的样式和标记，并改造样式以适配多页文档（避免污染正文）。"""
    raw = COVER.read_text(encoding="utf-8")
    # 先去掉 HTML 注释——注释里出现的字面量 <body> 会干扰下面的标签匹配
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
    style = re.search(r"<style>(.*?)</style>", raw, re.S).group(1)
    body = re.search(r"<body>(.*?)</body>", raw, re.S).group(1)

    # 1) 移除封面自带的 @page（整本书的分页由下方书籍 CSS 统一定义）
    style = re.sub(r"@page\s*\{[^}]*\}", "", style, count=1)
    # 2) 通配符重置只能作用于封面内部，否则会清掉正文所有边距
    style = style.replace("* { margin: 0; padding: 0; box-sizing: border-box; }",
                          ".cover, .cover * { margin: 0; padding: 0; box-sizing: border-box; }")
    # 3) 原 html,body 负责的字体/底色/尺寸，改挂到 .cover 上
    style = style.replace("html, body {", ".cover {")

    return style, body


def render_readme() -> str:
    """README.md → HTML 正文。"""
    text = README.read_text(encoding="utf-8")
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
        output_format="html5",
    )
    return md.convert(text)


# 整本书的打印 CSS：封面命名页满版，正文页带页边距
BOOK_CSS = """
  /* 默认页：正文，A4 + 页边距 */
  @page { size: A4; margin: 16mm 15mm 15mm 15mm; }
  /* 命名页：封面满版无边距 */
  @page coverpage { size: A4; margin: 0; }

  .cover-page { page: coverpage; break-after: page; }

  body {
    font-family: "PingFang SC", "Songti SC", -apple-system, "Helvetica Neue", system-ui, sans-serif;
    font-size: 10.5pt;
    line-height: 1.75;
    color: #1f1c18;
    -webkit-font-smoothing: antialiased;
  }

  /* 正文容器（封面不受影响） */
  .content { }

  .content h1, .content h2, .content h3,
  .content h4, .content h5, .content h6 {
    font-weight: 700;
    line-height: 1.35;
    break-after: avoid;
    color: #16130f;
  }
  .content h1 { font-size: 23pt; margin: 0 0 8mm; padding-bottom: 4mm; border-bottom: 3px solid #f2660a; }
  .content h2 {
    font-size: 17pt; margin: 11mm 0 4mm;
    padding-left: 4mm; border-left: 6px solid #f2660a;
    break-before: page;            /* 每个一级篇章另起一页 */
  }
  .content h2:first-of-type { break-before: avoid; }
  .content h3 { font-size: 13.5pt; margin: 7mm 0 3mm; color: #c64e00; }
  .content h4 { font-size: 11.5pt; margin: 5mm 0 2.5mm; }
  .content h5, .content h6 { font-size: 10.5pt; margin: 4mm 0 2mm; color: #4b463f; }

  .content p { margin: 0 0 2.6mm; }
  .content ul, .content ol { margin: 0 0 3mm; padding-left: 7mm; }
  .content li { margin: 0 0 1mm; }

  .content blockquote {
    margin: 3mm 0; padding: 2mm 4mm;
    background: #fff6ef; border-left: 4px solid #f2660a;
    color: #4b463f;
  }
  .content blockquote p { margin: 0; }

  /* 表格 */
  .content table {
    width: 100%; border-collapse: collapse;
    margin: 3mm 0 4mm; font-size: 9.5pt;
    break-inside: auto;
  }
  .content th, .content td {
    border: 1px solid #e0dacf; padding: 1.6mm 2.4mm;
    text-align: left; vertical-align: top;
  }
  .content thead th { background: #f7efe6; color: #16130f; font-weight: 700; }
  .content tr { break-inside: avoid; }

  /* 行内代码与围栏代码 */
  .content code {
    font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 9pt; background: #f2efe9; padding: 0.4mm 1mm; border-radius: 2px;
  }
  .content pre {
    background: #1f1c18; color: #f4efe8;
    padding: 3mm 4mm; border-radius: 4px;
    margin: 2.5mm 0 4mm; overflow: hidden;
    break-inside: avoid; white-space: pre-wrap; word-break: break-word;
  }
  .content pre code { background: transparent; color: inherit; font-size: 8.6pt; padding: 0; }

  /* 图片：居中、限宽、不跨页断裂 */
  .content p[align="center"] { text-align: center; margin: 3mm 0; break-inside: avoid; }
  .content img { max-width: 100%; height: auto; border: 1px solid #ececec; border-radius: 3px; }

  .content hr { border: none; border-top: 1px solid #e0dacf; margin: 5mm 0; }

  .content a { color: #c64e00; text-decoration: none; }

  /* R2 上的在线资源链接（视频播放 / PPT 下载等）：在 PDF 里渲染成醒目的橙色按钮 */
  .content a[href*="r2notes.bozhouai.com"] {
    display: inline-block;
    margin: 1mm 0 3mm;
    padding: 2.6mm 7mm;
    background: #f2660a;
    color: #ffffff;
    font-weight: 700;
    font-size: 11.5pt;
    border-radius: 4px;
    letter-spacing: 0.02em;
  }

  /* 顶部目录区适当紧凑 */
  .content > h2#目录 + ul, .content ul ul { font-size: 10pt; }
"""


def build() -> None:
    cover_style, cover_body = extract_cover()
    content_html = render_readme()
    validate_cover_style(cover_style)
    validate_html_fragment(cover_body, "cover.html")
    validate_html_fragment(content_html, "README.md")

    document = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="{CONTENT_SECURITY_POLICY}">
<title>Codex 橙皮书</title>
<style>
{cover_style}
{BOOK_CSS}
</style>
</head>
<body>
  <div class="cover-page">
{cover_body}
  </div>
  <main class="content">
{content_html}
  </main>
</body>
</html>
"""
    BOOK_HTML.write_text(document, encoding="utf-8")
    print(f"已生成 {BOOK_HTML.relative_to(ROOT)}（{len(document)} 字节）")

    subprocess.run(
        [
            CHROME,
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={OUTPUT_PDF}",
            BOOK_HTML.as_uri(),
        ],
        check=True,
        capture_output=True,
        timeout=CHROME_TIMEOUT_SECONDS,
    )
    size_kb = OUTPUT_PDF.stat().st_size / 1024
    print(f"已导出 {OUTPUT_PDF.name}（{size_kb:.0f} KB）")


if __name__ == "__main__":
    build()
