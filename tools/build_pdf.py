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
import shutil
import subprocess
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
COVER = ROOT / "cover.html"
BOOK_HTML = ROOT / "book.html"
OUTPUT_PDF = ROOT / "Codex橙皮书.pdf"

# 常见的 Chrome/Chromium 可执行文件位置（macOS / Linux）。
# 可用环境变量 CHROME 覆盖，方便在 CI、云端或自定义安装路径下使用。
_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome-stable",
    "/usr/bin/google-chrome-stable",
    "google-chrome",
    "chromium",
    "chromium-browser",
    "/usr/bin/google-chrome",
)


def resolve_chrome() -> str:
    """定位可用的 Chrome/Chromium：优先 CHROME 环境变量，其次按候选列表探测。"""
    env_chrome = os.environ.get("CHROME")
    if env_chrome:
        found = shutil.which(env_chrome) or (env_chrome if Path(env_chrome).exists() else None)
        if found:
            return found
        raise FileNotFoundError(f"环境变量 CHROME 指定的可执行文件不存在：{env_chrome}")

    for candidate in _CHROME_CANDIDATES:
        found = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if found:
            return found

    raise FileNotFoundError(
        "未找到 Chrome/Chromium。请安装 Google Chrome，或用环境变量 CHROME "
        "指定可执行文件路径，例如 CHROME=google-chrome python3 tools/build_pdf.py。"
    )


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

    document = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
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

    chrome = resolve_chrome()
    subprocess.run(
        [
            chrome,
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={OUTPUT_PDF}",
            BOOK_HTML.as_uri(),
        ],
        check=True,
        capture_output=True,
    )
    size_kb = OUTPUT_PDF.stat().st_size / 1024
    print(f"已导出 {OUTPUT_PDF.name}（{size_kb:.0f} KB）")


if __name__ == "__main__":
    build()
