#!/usr/bin/env python3
"""
build_docx.py
--------------------------------------------------------------------------
Turn the report's Markdown source into a .docx.

The report is written in Markdown and delivered as .docx. Writing it directly in a word
processor would mean re-applying formatting by hand after every correction, and the
corrections are frequent -- every number in the report is checked against
report_numbers.json and some of them move. Markdown also keeps the source in version
control, where a diff shows what changed between drafts.

The route is Markdown -> HTML -> LibreOffice -> docx. Pandoc would be one step shorter
but is not installed here and needs root to install; LibreOffice is already present and
reads HTML natively, keeping tables, headings, code blocks and lists intact.

The stylesheet below is not decoration. LibreOffice maps HTML elements onto Word styles,
so what is set here is what the delivered document's styles look like: body text,
headings, tables with visible borders, and monospaced code blocks that do not wrap
mid-token.

Usage:
  python3 build_docx.py                       # -> the .docx beside the .md
  python3 build_docx.py --html-only           # stop at HTML, for a quick look
--------------------------------------------------------------------------
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "IoMT-ag-saldiri-tespiti-raporu.md"

CSS = """
@page { size: A4; margin: 2.5cm 2.2cm; }
body  { font-family: "Liberation Serif", serif; font-size: 11.5pt; line-height: 1.45;
        text-align: justify; }
h1    { font-family: "Liberation Sans", sans-serif; font-size: 20pt; margin: 0 0 4pt 0; }
h2    { font-family: "Liberation Sans", sans-serif; font-size: 15pt;
        margin: 20pt 0 6pt 0; border-bottom: 1px solid #999; padding-bottom: 2pt; }
h3    { font-family: "Liberation Sans", sans-serif; font-size: 12.5pt; margin: 14pt 0 4pt 0; }
p     { margin: 0 0 7pt 0; }
/* Tables carry most of the results, so borders are explicit: LibreOffice's default for
   an unstyled HTML table is borderless, which turns a results table into loose text. */
table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 10pt; }
th, td{ border: 0.5pt solid #666; padding: 3pt 5pt; text-align: left;
        vertical-align: top; }
th    { background: #ececec; font-weight: bold; }
pre   { font-family: "Liberation Mono", monospace; font-size: 9pt; background: #f4f4f4;
        border: 0.5pt solid #ccc; padding: 6pt; white-space: pre-wrap; line-height: 1.25; }
code  { font-family: "Liberation Mono", monospace; font-size: 9.5pt; }
pre code { font-size: 9pt; }
blockquote { margin: 6pt 0 6pt 12pt; padding-left: 10pt; border-left: 2pt solid #bbb;
             color: #333; font-style: italic; }
li    { margin-bottom: 3pt; }
hr    { border: none; border-top: 0.5pt solid #bbb; margin: 14pt 0; }
img   { max-width: 100%; }
"""


def to_html(md_text):
    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists", "attr_list", "toc"],
    )
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<style>{CSS}</style></head><body>{body}</body></html>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(SOURCE))
    ap.add_argument("--html-only", action="store_true")
    args = ap.parse_args()

    src = Path(args.source)
    if not src.exists():
        sys.exit(f"not found: {src}")

    html_path = src.with_suffix(".html")
    html_path.write_text(to_html(src.read_text()), encoding="utf-8")
    print(f"html  -> {html_path}")
    if args.html_only:
        return

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        sys.exit("LibreOffice not found; cannot produce .docx")

    # LibreOffice writes <stem>.docx into --outdir and refuses to be told a filename.
    subprocess.run([soffice, "--headless", "--convert-to", "docx:MS Word 2007 XML",
                    "--outdir", str(src.parent), str(html_path)],
                   check=True, capture_output=True)
    out = src.with_suffix(".docx")
    if not out.exists():
        sys.exit("conversion reported success but produced no .docx")
    print(f"docx  -> {out}  ({out.stat().st_size / 1024:.0f} KB)")
    print("\nOpen it and apply page numbers, a table of contents and a title page in "
          "LibreOffice; those are the parts a converter should not guess at.")


if __name__ == "__main__":
    main()
