#!/usr/bin/env python3
"""Build the Galileo User Manual PDF.

Pipeline:  Markdown chapters (mostly the Galileo wiki)  ->  one HTML document
           ->  Microsoft Edge / Chrome (via Playwright)  ->  PDF  ->  pypdf
           (front/rear covers merged in).

Usage:  python build_manual.py [--version X] [--output FILE] [--only 06,07]
                               [--html-only] [--refresh-images]
See README.md for details.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import re
import sys
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
CACHE = BUILD / "image-cache"
RAW_PREFIX = "https://raw.githubusercontent.com/gordtulloch/Galileo/main/"


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
def load_config() -> dict:
    with open(ROOT / "manual.toml", "rb") as fh:
        cfg = tomllib.load(fh)
    return cfg


def resolve_dir(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (ROOT / p).resolve()


def auto_version(galileo: Path) -> str:
    try:
        with open(galileo / "pyproject.toml", "rb") as fh:
            return tomllib.load(fh)["project"]["version"]
    except Exception:
        return "unreleased"


# --------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------
def resolve_image(src: str, galileo: Path, refresh: bool) -> str:
    """Return a file:// URI for an image, preferring local copies.

    Order: images/<basename> override -> Galileo repo checkout (for raw
    GitHub URLs) -> downloaded cache.  Unresolvable images are left as-is.
    """
    if not src.startswith(("http://", "https://")):
        return src
    path = urllib.parse.unquote(urllib.parse.urlparse(src).path)
    base = Path(path).name

    override = ROOT / "images" / base
    if override.is_file():
        return override.as_uri()

    if src.startswith(RAW_PREFIX):
        local = galileo / urllib.parse.unquote(src[len(RAW_PREFIX):])
        if local.is_file():
            return local.as_uri()

    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / re.sub(r"[^\w.\-]+", "_", urllib.parse.unquote(src.split("://", 1)[1]))
    if refresh or not cached.is_file():
        try:
            req = urllib.request.Request(src, headers={"User-Agent": "galileo-manual-build"})
            with urllib.request.urlopen(req, timeout=30) as r:
                cached.write_bytes(r.read())
        except Exception as exc:  # noqa: BLE001
            print(f"  ! could not fetch image {src}: {exc}", file=sys.stderr)
            return src
    return cached.as_uri()


# --------------------------------------------------------------------------
# Markdown -> HTML
# --------------------------------------------------------------------------
def gh_slug(text: str, sep: str = "-") -> str:
    """GitHub-style heading slug, so wiki anchor links keep working."""
    text = re.sub(r"<[^>]+>", "", text).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", sep)


def new_markdown() -> markdown.Markdown:
    return markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "attr_list", "toc"],
        extension_configs={"toc": {"slugify": gh_slug, "permalink": False}},
    )


def clean_source(text: str) -> str:
    """Drop wiki-only furniture that is redundant in a printed manual."""
    # Per-article "Contents" lists: the manual has its own table of contents.
    text = re.sub(r"^##\s+Contents\s*\n(?:[ \t]*[-*][^\n]*\n|[ \t]*\n)+", "", text, flags=re.M)
    # Horizontal rules used as wiki section separators.
    text = re.sub(r"^\s*---+\s*$", "", text, flags=re.M)
    return text


def split_title(text: str, fallback: str) -> tuple[str, str]:
    m = re.search(r"^#\s+(.+?)\s*$", text, flags=re.M)
    if not m:
        return fallback, text
    title = re.sub(r"^\d+\.\s*", "", m.group(1)).strip()
    return title, text[: m.start()] + text[m.end():]


class Chapter:
    def __init__(self, entry: dict, index: int, appendix_index: int, cfg_paths: dict):
        self.entry = entry
        if "wiki" in entry:
            self.source = resolve_dir(cfg_paths["wiki"]) / entry["wiki"]
            self.page_name = Path(entry["wiki"]).stem
        else:
            self.source = ROOT / entry["file"]
            self.page_name = Path(entry["file"]).stem
        self.slug = "ch-" + gh_slug(self.page_name.replace(".", ""))
        self.appendix = bool(entry.get("appendix"))
        self.label = (
            f"Appendix {chr(ord('A') + appendix_index)}" if self.appendix else f"Chapter {index}"
        )
        self.title = ""
        self.body = ""
        self.headings: list[tuple[int, str, str]] = []  # (level, id, text)


def render_chapter(ch: Chapter, page_map: dict[str, str], galileo: Path, refresh: bool) -> None:
    raw = ch.source.read_text(encoding="utf-8")
    title, raw = split_title(clean_source(raw), ch.source.stem)
    ch.title = ch.entry.get("title", title)

    md = new_markdown()
    body = md.convert(raw)
    pfx = ch.slug + "--"

    # Namespace heading ids per chapter and record them for the TOC.
    def head(m: re.Match) -> str:
        level, hid, inner = int(m.group(1)), m.group(2), m.group(3)
        text = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        ch.headings.append((level, pfx + hid, text))
        return f'<h{level} id="{pfx}{hid}">{inner}</h{level}>'

    body = re.sub(r'<h([1-6]) id="([^"]+)">(.*?)</h\1>', head, body, flags=re.S)

    # Links: in-page anchors and cross-page wiki links.
    def href(m: re.Match) -> str:
        target = html.unescape(m.group(1))
        if target.startswith("#"):
            return f'href="#{pfx}{target[1:]}"'
        if re.match(r"^[a-z][a-z0-9+.\-]*:", target, flags=re.I):
            return m.group(0)
        page, _, frag = target.partition("#")
        page = urllib.parse.unquote(page)
        if page in page_map:
            return f'href="#{page_map[page]}--{frag}"' if frag else f'href="#{page_map[page]}"'
        return 'data-unlinked="1"'  # page not in the manual; neutralised below

    body = re.sub(r'href="([^"]*)"', href, body)
    body = re.sub(r'<a data-unlinked="1">(.*?)</a>', r"\1", body, flags=re.S)
    body = re.sub(r'<a data-unlinked="1"[^>]*>(.*?)</a>', r"\1", body, flags=re.S)

    # Images: local resolution, and figure/caption from alt text.
    def img(m: re.Match) -> str:
        attrs = m.group(1)
        src_m = re.search(r'src="([^"]*)"', attrs)
        if src_m:
            new = resolve_image(html.unescape(src_m.group(1)), galileo, refresh)
            attrs = attrs.replace(src_m.group(0), f'src="{html.escape(new, quote=True)}"')
        return f"<img{attrs}>"

    body = re.sub(r"<img([^>]*?)\s*/?>", img, body)

    def figure(m: re.Match) -> str:
        tag = m.group(1)
        alt = re.search(r'alt="([^"]*)"', tag)
        cap = f"<figcaption>{alt.group(1)}</figcaption>" if alt and alt.group(1).strip() else ""
        return f"<figure>{tag}{cap}</figure>"

    body = re.sub(r"<p>\s*(<img[^>]*>)\s*</p>", figure, body)

    # Wiki "Overview" blockquote about built-in help is wiki-specific wording.
    ch.body = body


# --------------------------------------------------------------------------
# HTML assembly
# --------------------------------------------------------------------------
def esc(s: str) -> str:
    return html.escape(s, quote=True)


def toc_html(chapters: list[Chapter], depth: int, pages: dict[str, int]) -> str:
    rows = []
    for ch in chapters:
        rows.append(
            f'<li class="toc-ch"><a href="#{ch.slug}"><span class="t"><b>{esc(ch.label)}</b>'
            f"&ensp;{esc(ch.title)}</span><span class=\"p\">{pages.get(ch.slug, '')}</span></a></li>"
        )
        if depth >= 2:
            for level, hid, text in ch.headings:
                if level == 2:
                    rows.append(
                        f'<li class="toc-sec"><a href="#{hid}"><span class="t">{esc(text)}</span>'
                        f"<span class=\"p\">{pages.get(hid, '')}</span></a></li>"
                    )
    return '<section class="toc"><h1 class="plain">Contents</h1><ul>' + "".join(rows) + "</ul></section>"


def build_html(cfg: dict, chapters: list[Chapter], pages: dict[str, int], front_matter: bool) -> str:
    m = cfg["manual"]
    css = (ROOT / "templates" / "style.css").read_text(encoding="utf-8")
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        f"<title>{esc(m['title'])} {esc(m['subtitle'])}</title><style>{css}</style></head><body>",
    ]
    if front_matter:
        parts.append(toc_html(chapters, int(m.get("toc_depth", 2)), pages))
    for ch in chapters:
        parts.append(
            f'<section class="chapter {"appendix" if ch.appendix else ""}" id="{ch.slug}">'
            f'<h1 data-label="{esc(ch.label)}">{esc(ch.title)}</h1>{ch.body}</section>'
        )
    parts.append("</body></html>")
    return "".join(parts)


def title_page_html(cfg: dict, version: str, cover: Path | None) -> str:
    m = cfg["manual"]
    css = (ROOT / "templates" / "style.css").read_text(encoding="utf-8")
    cover_html = (
        f'<div class="cover"><img src="{cover.as_uri()}"></div>' if cover and cover.is_file() else ""
    )
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>
{cover_html}
<div class="titlepage">
  <h1 class="plain big">{esc(m['title'])}</h1>
  <p class="sub">{esc(m['subtitle'])}</p>
  <p class="ver">Version {esc(version)}</p>
  <p class="date">{dt.date.today():%B %Y}</p>
  <p class="copy">{esc(m.get('copyright', ''))}</p>
</div></body></html>"""


def rear_cover_html(cover: Path | None) -> str:
    css = (ROOT / "templates" / "style.css").read_text(encoding="utf-8")
    body = f'<div class="cover"><img src="{cover.as_uri()}"></div>' if cover and cover.is_file() else ""
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>{body}</body></html>"


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------
def launch_browser(pw):
    last = None
    for channel in ("msedge", "chrome"):
        try:
            return pw.chromium.launch(channel=channel)
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise SystemExit(
        "Could not start Microsoft Edge or Google Chrome via Playwright.\n"
        f"Install one of them (Edge ships with Windows 11). Last error: {last}"
    )


def footer_template(title: str) -> str:
    return (
        "<div style=\"font-family:'Segoe UI',Arial,sans-serif;font-size:8px;color:#666;"
        "width:100%;padding:0 0.8in;display:flex;justify-content:space-between;\">"
        f"<span>{esc(title)}</span><span class='pageNumber'></span></div>"
    )


def render_pdf(browser, html_path: Path, out: Path, page_size: str, footer: str | None) -> None:
    page = browser.new_page()
    page.goto(html_path.as_uri(), wait_until="networkidle")
    page.wait_for_function("Array.from(document.images).every(i => i.complete)")
    opts = dict(path=str(out), format=page_size, print_background=True, outline=True, tagged=True)
    if footer:
        opts.update(
            display_header_footer=True,
            header_template="<div></div>",
            footer_template=footer,
            margin=dict(top="0.8in", bottom="0.9in", left="0.8in", right="0.8in"),
        )
    else:
        opts.update(margin=dict(top="0", bottom="0", left="0", right="0"))
    page.pdf(**opts)
    page.close()


def heading_pages(pdf: Path, expected: list[tuple[str, str]]) -> dict[str, int]:
    """Map heading ids to page numbers using the PDF's own bookmarks."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf))
    flat: list[tuple[str, int]] = []

    def walk(items):
        for it in items:
            if isinstance(it, list):
                walk(it)
            else:
                title = " ".join(it.title.split())
                half = len(title) // 2
                # Chromium sometimes emits a heading's text twice in the bookmark.
                if len(title) % 2 == 0 and title[:half] == title[half:]:
                    title = title[:half]
                flat.append((title, reader.get_destination_page_number(it) + 1))

    walk(reader.outline)
    result: dict[str, int] = {}
    cursor = 0
    for hid, text in expected:
        want = " ".join(text.split())
        for i in range(cursor, len(flat)):
            if flat[i][0] == want:
                result[hid] = flat[i][1]
                cursor = i + 1
                break
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the Galileo User Manual PDF")
    ap.add_argument("--version", help="version shown on the title page (default: manual.toml / Galileo pyproject)")
    ap.add_argument("--output", help="output PDF path (default: from manual.toml)")
    ap.add_argument("--only", help="comma-separated chapter number prefixes to build, e.g. 06,07 (fast iteration)")
    ap.add_argument("--html-only", action="store_true", help="write build/manual.html and stop")
    ap.add_argument("--refresh-images", action="store_true", help="re-download cached remote images")
    args = ap.parse_args()

    cfg = load_config()
    m = cfg["manual"]
    galileo = resolve_dir(cfg["paths"]["galileo"])
    version = args.version or m.get("version", "auto")
    if version == "auto":
        version = auto_version(galileo)

    entries = cfg["chapter"]
    if args.only:
        wanted = tuple(x.strip() for x in args.only.split(","))
        entries = [e for e in entries if Path(e.get("wiki", e.get("file", ""))).name.startswith(wanted)]
        if not entries:
            raise SystemExit(f"--only {args.only!r} matched no chapters")

    chapters, n, a = [], 0, 0
    for e in entries:
        is_app = bool(e.get("appendix"))
        chapters.append(Chapter(e, n + 1, a, cfg["paths"]))
        if is_app:
            a += 1
        else:
            n += 1
    page_map = {c.page_name: c.slug for c in chapters}

    BUILD.mkdir(exist_ok=True)
    for ch in chapters:
        print(f"  {ch.label:<11} {ch.source.name}")
        render_chapter(ch, page_map, galileo, args.refresh_images)

    expected: list[tuple[str, str]] = []
    for ch in chapters:
        expected.append((ch.slug, ch.title))
        if int(m.get("toc_depth", 2)) >= 2:
            expected += [(hid, t) for lvl, hid, t in ch.headings if lvl == 2]

    body_html = BUILD / "manual.html"
    body_html.write_text(build_html(cfg, chapters, {}, True), encoding="utf-8")
    if args.html_only:
        print(f"Wrote {body_html}")
        return 0

    from playwright.sync_api import sync_playwright
    from pypdf import PdfReader, PdfWriter

    out = resolve_dir(args.output) if args.output else resolve_dir(m.get("output", "build/Galileo-Manual.pdf"))
    out.parent.mkdir(parents=True, exist_ok=True)
    footer = footer_template(f"{m['title']} {m['subtitle']} — v{version}")
    page_size = m.get("page_size", "Letter")
    front_cover = ROOT / m["front_cover"] if m.get("front_cover") else None
    rear_cover = ROOT / m["rear_cover"] if m.get("rear_cover") else None

    with sync_playwright() as pw:
        browser = launch_browser(pw)
        try:
            # Pass 1 finds page numbers; pass 2 prints the TOC with them.
            body_pdf = BUILD / "body.pdf"
            print("Rendering body (pass 1)...")
            render_pdf(browser, body_html, body_pdf, page_size, footer)
            pages = heading_pages(body_pdf, expected)
            missing = [h for h, _ in expected if h not in pages]
            if missing:
                print(f"  ! {len(missing)} headings not found in PDF bookmarks (TOC page blank)", file=sys.stderr)
            body_html.write_text(build_html(cfg, chapters, pages, True), encoding="utf-8")
            print("Rendering body (pass 2)...")
            render_pdf(browser, body_html, body_pdf, page_size, footer)

            front_html = BUILD / "front.html"
            front_html.write_text(title_page_html(cfg, version, front_cover), encoding="utf-8")
            front_pdf = BUILD / "front.pdf"
            render_pdf(browser, front_html, front_pdf, page_size, None)

            rear_pdf = None
            if rear_cover and rear_cover.is_file():
                rear_html = BUILD / "rear.html"
                rear_html.write_text(rear_cover_html(rear_cover), encoding="utf-8")
                rear_pdf = BUILD / "rear.pdf"
                render_pdf(browser, rear_html, rear_pdf, page_size, None)
        finally:
            browser.close()

    writer = PdfWriter()
    for part in (front_pdf, body_pdf, rear_pdf):
        if part:
            writer.append(str(part), import_outline=(part == body_pdf))
    writer.add_metadata({"/Title": f"{m['title']} {m['subtitle']}", "/Author": m.get("author", ""),
                         "/Subject": f"Version {version}"})
    with open(out, "wb") as fh:
        writer.write(fh)
    print(f"Wrote {out} ({len(PdfReader(str(out)).pages)} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
