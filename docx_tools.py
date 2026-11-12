#!/usr/bin/env python3
"""Word <-> Markdown tooling for the Galileo manual (Word is the source of truth).

Commands
  reference     Regenerate templates/reference.docx (the Word styles new chapters are created with).
  seed          One-time: create chapters/*.docx from the wiki Markdown named in manual.toml.
  export-wiki   Convert chapters/*.docx to wiki Markdown (default: build/wiki-export; --to-wiki writes
                straight into the wiki checkout).

Also imported by build_manual.py, which converts each .docx to Markdown with `docx_to_md` before rendering.
Requires pandoc (winget install JohnMacFarlane.Pandoc).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import os
import re
import shutil
import subprocess
import sys
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
RAW_PREFIX = "https://raw.githubusercontent.com/gordtulloch/Galileo/main/"


# --------------------------------------------------------------------------
# pandoc
# --------------------------------------------------------------------------
def pandoc_exe() -> str:
    found = shutil.which("pandoc")
    if found:
        return found
    for cand in (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Pandoc" / "pandoc.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Pandoc" / "pandoc.exe",
    ):
        if cand.is_file():
            return str(cand)
    raise SystemExit("pandoc not found. Install it with:  winget install JohnMacFarlane.Pandoc")


def run_pandoc(*args: str) -> None:
    proc = subprocess.run([pandoc_exe(), *args], capture_output=True, text=True, encoding="utf-8")
    if proc.returncode:
        raise SystemExit(f"pandoc failed ({' '.join(args[:4])} ...):\n{proc.stderr}")
    if proc.stderr.strip():
        print("  pandoc:", proc.stderr.strip().splitlines()[0], file=sys.stderr)


def load_config() -> dict:
    with open(ROOT / "manual.toml", "rb") as fh:
        return tomllib.load(fh)


def resolve_dir(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (ROOT / p).resolve()


def chapters_dir(cfg: dict) -> Path:
    return resolve_dir(cfg["paths"].get("docx", "chapters"))


# --------------------------------------------------------------------------
# docx -> Markdown
# --------------------------------------------------------------------------
def _attr(tag: str, name: str) -> str:
    m = re.search(rf'\b{name}="([^"]*)"', tag)
    return m.group(1) if m else ""


def normalise_pandoc_md(text: str) -> str:
    """Turn pandoc's <figure>/<img> HTML back into plain Markdown images."""
    def md_image(tag: str) -> str:
        return f"![{html.unescape(_attr(tag, 'alt'))}]({_attr(tag, 'src').replace(' ', '%20')})"

    # The figure caption is the image's alt text, so the wrapper adds nothing.
    text = re.sub(r"<figure>\s*(<img[^>]*>)\s*<figcaption.*?</figcaption>\s*</figure>",
                  lambda m: md_image(m.group(1)), text, flags=re.S)
    text = re.sub(r"<img[^>]*>", lambda m: md_image(m.group(0)), text)
    # pandoc escapes ">" ("Equipment \> Camera"); only a leading ">" needs it (it would start a quote).
    text = re.sub(r"(?m)(?<!^)\\>", ">", text)
    # pandoc pads numbered-list markers ("1.  Open"); the wiki uses a single space.
    text = re.sub(r"(?m)^(\s*\d+\.)[ ]{2,}(?=\S)", r"\1 ", text)
    return _restore_numbered_anchors(text)


def _restore_numbered_anchors(text: str) -> str:
    """pandoc drops a heading's leading number from its anchor ("4. Foo" -> #foo); the wiki's GitHub-style
    anchors keep it (#4-foo). Re-point such in-page links at the heading's real slug."""
    slugs = set()
    fenced = False
    for line in text.split("\n"):
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
        elif not fenced:
            m = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
            if m:
                slugs.add(gh_slug(m.group(1)))
    stripped = {re.sub(r"^\d+-", "", s): s for s in slugs if re.match(r"^\d+-", s)}

    def fix(m: re.Match) -> str:
        frag = m.group(1)
        return m.group(0) if frag in slugs or frag not in stripped else f"](#{stripped[frag]})"

    return re.sub(r"\]\(#([^)\s]+)\)", fix, text)


def docx_to_md(docx: Path, media_dir: Path) -> str:
    """Convert a chapter .docx to GitHub-flavoured Markdown; images are extracted into media_dir.

    Tracked changes are accepted. Image links in the result are absolute paths under media_dir.
    """
    if media_dir.exists():
        shutil.rmtree(media_dir)
    media_dir.parent.mkdir(parents=True, exist_ok=True)
    out = media_dir.parent / (media_dir.name + ".md")
    run_pandoc(str(docx), "-f", "docx", "-t", "gfm", "--wrap=none", "--track-changes=accept",
               "--lua-filter", str(ROOT / "templates" / "fence.lua"),
               f"--extract-media={media_dir.as_posix()}", "-o", str(out))
    return normalise_pandoc_md(out.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Markdown -> docx
# --------------------------------------------------------------------------
def md_to_docx(md_text: str, out: Path, reference: Path | None) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = BUILD / "seed" / (out.stem + ".md")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(md_text, encoding="utf-8")
    args = [str(tmp), "-f", "gfm+implicit_figures", "-t", "docx", "-o", str(out)]
    if reference and reference.is_file():
        args += ["--reference-doc", str(reference)]
    run_pandoc(*args)


# --------------------------------------------------------------------------
# reference.docx
# --------------------------------------------------------------------------
def make_reference(path: Path) -> None:
    """Pandoc's default reference.docx, restyled to match the printed manual."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor

    path.parent.mkdir(parents=True, exist_ok=True)
    run_pandoc("-o", str(path), "--print-default-data-file", "reference.docx")
    doc = Document(str(path))
    accent, ink, muted = RGBColor(0x1F, 0x4E, 0x8C), RGBColor(0x1C, 0x1F, 0x24), RGBColor(0x5B, 0x64, 0x70)

    def font(style, name="Segoe UI", size=None, color=None, bold=None, italic=None):
        f = style.font
        f.name = name
        rpr = style.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            from docx.oxml import OxmlElement
            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rfonts.set(qn(a), name)
        for a in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
            if rfonts.get(qn(a)) is not None:
                del rfonts.attrib[qn(a)]
        if size:
            f.size = Pt(size)
        if color is not None:
            f.color.rgb = color
        if bold is not None:
            f.bold = bold
        if italic is not None:
            f.italic = italic

    styles = {s.name: s for s in doc.styles}
    for name in ("Normal", "Body Text", "First Paragraph", "Compact"):
        if name in styles:
            font(styles[name], size=10.5, color=ink)
    for name in ("Body Text", "First Paragraph"):
        if name in styles:
            styles[name].paragraph_format.space_after = Pt(6)
            styles[name].paragraph_format.line_spacing = 1.25
    sizes = {"Heading 1": 26, "Heading 2": 16, "Heading 3": 12.5, "Heading 4": 11, "Title": 28}
    for name, size in sizes.items():
        if name in styles:
            font(styles[name], size=size, color=accent if name != "Heading 4" else muted, bold=True)
            styles[name].paragraph_format.space_before = Pt(18 if name != "Heading 1" else 0)
            styles[name].paragraph_format.space_after = Pt(6)
    for name in ("Source Code", "Verbatim Char"):
        if name in styles:
            font(styles[name], name="Cascadia Mono", size=9)
    if "Block Text" in styles:
        font(styles["Block Text"], size=10.5, color=ink)
        styles["Block Text"].paragraph_format.left_indent = Inches(0.25)
    for name in ("Image Caption", "Table Caption", "Caption"):
        if name in styles:
            font(styles[name], size=9, color=muted, italic=True)
    if "Captioned Figure" in styles:
        styles["Captioned Figure"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if "Hyperlink" in styles:
        styles["Hyperlink"].font.color.rgb = accent
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.left_margin = sec.right_margin = Inches(0.8)
    sec.top_margin, sec.bottom_margin = Inches(0.8), Inches(0.9)
    doc.save(str(path))


# --------------------------------------------------------------------------
# seed: wiki Markdown -> chapters/*.docx
# --------------------------------------------------------------------------
def entry_stem(e: dict) -> str:
    return Path(e.get("docx") or e.get("wiki") or e.get("file")).stem


def cmd_seed(args: argparse.Namespace) -> int:
    import build_manual as bm

    cfg = load_config()
    wiki = resolve_dir(cfg["paths"]["wiki"])
    galileo = resolve_dir(cfg["paths"]["galileo"])
    ref = ROOT / "templates" / "reference.docx"
    if not ref.is_file():
        print("Creating templates/reference.docx ...")
        make_reference(ref)
    out_dir = chapters_dir(cfg)
    names: list[str] = []
    for e in cfg["chapter"]:
        for n in [e.get("wiki") or e.get("docx"), *e.get("append", [])]:
            n = n and Path(n).stem + ".md"  # the source is always the wiki's Markdown article
            if n and n not in names:
                names.append(n)
    for name in names:
        stem = Path(name).stem
        if args.only and not stem.startswith(tuple(args.only.split(","))):
            continue
        dest = out_dir / f"{stem}.docx"
        if dest.exists() and not args.force:
            print(f"  skip {dest.name} (exists; use --force to overwrite)")
            continue
        text = bm.clean_source((wiki / name).read_text(encoding="utf-8"))

        def local(m: re.Match) -> str:
            uri = bm.resolve_image(m.group(2), galileo, False)
            if uri.startswith("file:"):
                path = urllib.request.url2pathname(urllib.parse.urlparse(uri).path).replace(chr(92), "/")
                return f"{m.group(1)}(<{path}>)"  # <...> allows spaces in the file name
            return m.group(0)

        text = re.sub(r"(!\[[^\]]*\])\(([^)\s]+)\)", local, text)
        md_to_docx(text, dest, ref)
        print(f"  wrote {dest.relative_to(ROOT)}")
    return 0


# --------------------------------------------------------------------------
# export-wiki: chapters/*.docx -> wiki Markdown
# --------------------------------------------------------------------------
def gh_slug(t: str) -> str:
    t = re.sub(r"<[^>]+>", "", t).strip().lower()
    t = re.sub(r"[^\w\- ]", "", t)
    return t.replace(" ", "-")


def make_contents(text: str) -> str:
    items, fenced = [], False
    for line in text.split("\n"):
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
            continue
        m = None if fenced else re.match(r"^(#{2,3})\s+(.+?)\s*$", line)
        if m and m.group(2).lower() != "contents":
            items.append(("  " if len(m.group(1)) == 3 else "") + f"- [{m.group(2)}](#{gh_slug(m.group(2))})")
    return "## Contents\n\n" + "\n".join(items) + "\n\n---\n\n" if len(items) > 1 else ""


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cmd_export(args: argparse.Namespace) -> int:
    cfg = load_config()
    galileo = resolve_dir(cfg["paths"]["galileo"])
    out_dir = resolve_dir(cfg["paths"]["wiki"]) if args.to_wiki else BUILD / "wiki-export"
    out_dir.mkdir(parents=True, exist_ok=True)
    new_images = BUILD / "wiki-export-new-images"

    known: dict[str, str] = {}  # image hash -> raw GitHub URL
    for p in (galileo / "assets").rglob("*"):
        if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".svg"):
            known[sha(p)] = RAW_PREFIX + urllib.parse.quote(p.relative_to(galileo).as_posix())

    seen: set[str] = set()
    unmatched = 0
    for e in cfg["chapter"]:
        stem = entry_stem(e)
        if "docx" not in e and not (chapters_dir(cfg) / f"{stem}.docx").is_file():
            continue
        if stem in seen or (args.only and not stem.startswith(tuple(args.only.split(",")))):
            continue
        seen.add(stem)
        src = chapters_dir(cfg) / f"{stem}.docx"
        md = docx_to_md(src, BUILD / "media" / stem)

        def img(m: re.Match) -> str:
            nonlocal unmatched
            path = Path(urllib.parse.unquote(m.group(2)))
            if not path.is_file():
                return m.group(0)
            url = known.get(sha(path))
            if url:
                return f"{m.group(1)}({url})"
            unmatched += 1
            new_images.mkdir(parents=True, exist_ok=True)
            name = f"{stem}-{path.name}"
            shutil.copy2(path, new_images / name)
            print(f"  ! {stem}: new image {name} is not in Galileo/assets - add it there and fix the link", file=sys.stderr)
            return f"{m.group(1)}({RAW_PREFIX}assets/screenshots/{name})"

        md = re.sub(r"(!\[[^\]]*\])\(([^)]+)\)", img, md)
        md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
        # Wiki articles carry a Contents list after the intro; regenerate it.
        md = re.sub(r"^## Contents\s*\n(?:[ \t]*[-*][^\n]*\n|[ \t]*\n)+", "", md, flags=re.M)
        md = re.sub(r"^\s*-{3,}\s*$", "", md, flags=re.M)
        m = re.search(r"^## ", md, flags=re.M)
        if m:
            md = md[: m.start()] + make_contents(md) + md[m.start():]
        (out_dir / f"{stem}.md").write_text(md, encoding="utf-8", newline="\n")
        print(f"  wrote {out_dir / (stem + '.md')}")
    if unmatched:
        print(f"{unmatched} new image(s) copied to {new_images}", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("reference", help="regenerate templates/reference.docx")
    s = sub.add_parser("seed", help="create chapters/*.docx from the wiki Markdown")
    s.add_argument("--force", action="store_true", help="overwrite existing .docx files")
    s.add_argument("--only", help="comma-separated number prefixes, e.g. 06,07")
    x = sub.add_parser("export-wiki", help="convert chapters/*.docx to wiki Markdown")
    x.add_argument("--to-wiki", action="store_true", help="write into the wiki checkout instead of build/wiki-export")
    x.add_argument("--only", help="comma-separated number prefixes")
    args = ap.parse_args()
    if args.cmd == "reference":
        make_reference(ROOT / "templates" / "reference.docx")
        print("Wrote templates/reference.docx")
        return 0
    return cmd_seed(args) if args.cmd == "seed" else cmd_export(args)


if __name__ == "__main__":
    sys.exit(main())
