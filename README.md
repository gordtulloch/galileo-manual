# Galileo User Manual

Source and build tooling for the Galileo manual shipped with each release. **The manual's source documents are
Word files in [`chapters/`](chapters)**; the printable PDF and the wiki's Markdown are both generated from them.
The PDF has a front cover, title page, table of contents with page numbers, the chapters (footer with
title/version/page number), a rear cover and PDF bookmarks.

## Workflow

1. **Edit** a chapter in Word: `chapters/NN.-Name.docx`. Use the built-in styles (Heading 1-3, Body Text, lists,
   tables, Source Code, Block Text for callouts) rather than manual formatting; that is what converts cleanly.
   Tracked changes are accepted when the PDF or Markdown is generated, so resolve comments first.
2. **Build the PDF:** `.\build.ps1` -> `build\Galileo-Manual.pdf`.
3. **Update the wiki** when the manual changes: `.\docx.ps1 export-wiki` writes Markdown to `build\wiki-export\`
   for review, or `.\docx.ps1 export-wiki --to-wiki` writes straight into `../Galileo.wiki` (then review and
   commit there).

```powershell
.\build.ps1                      # full PDF
.\build.ps1 --version 1.0.0      # override the version on the title page
.\build.ps1 --only 06,07         # just those chapters, for quick layout iteration
.\build.ps1 --html-only          # write build\manual.html only (open in a browser)
.\docx.ps1 export-wiki --only 06 # one chapter's wiki Markdown
.\docx.ps1 seed --force          # re-create ALL chapters from the wiki (destroys edits!)
```

Requirements: Python 3.11+, Microsoft Edge (included with Windows 11) or Chrome, and
[pandoc](https://pandoc.org/) (`winget install JohnMacFarlane.Pandoc`). The first run creates `.venv` and installs
`markdown`, `playwright`, `pypdf` and `python-docx`; Playwright drives the **installed** Edge/Chrome.

## Things to know when editing in Word

- **Chapters are one-to-one with wiki articles** and keep the wiki's file names (`06.-Imaging.docx` ->
  `06.-Imaging.md`). Chapter order, appendices, version and covers are in `manual.toml`.
- **Links between chapters** are hyperlinks whose address is the wiki page name and heading anchor, e.g.
  `14.-Built-in-Help` or `02.-Getting-Started#where-galileo-keeps-its-files`. They are dead inside Word but are
  turned into working in-document links in the PDF and correct wiki links in the export. Keep that form when you
  add one. Links within a chapter use Word's normal cross-references/bookmarks.
- **Screenshots** are embedded in the document, with the image's *Alt Text* as its printed caption. On export,
  a picture that is identical to one in `../Galileo/assets/` becomes the usual raw GitHub link; a **new** picture is
  copied to `build\wiki-export-new-images\` with a warning - add it to the Galileo repo's `assets/screenshots/`
  and fix the link before publishing the wiki.
- **The table of contents is generated** - don't write one in Word. A "Contents" list at the top of a chapter
  is dropped from the PDF and regenerated in the wiki export.
- **Round trips are close, not byte-identical.** Headings, lists, tables, code, bold/italic, links and images
  survive; code blocks lose their language label (Python is detected), tables are re-padded, bare URLs get
  `<...>`. Wiki articles that went through Word will show those small diffs once.
- Styles for new chapters come from `templates/reference.docx` (`.\docx.ps1 reference` regenerates it).

## How the PDF is built

`build_manual.py` converts each `.docx` to Markdown (pandoc, extracting images into `build/media/`), namespaces
heading ids per chapter, rewrites wiki cross-links into in-document links, drops wiki-only furniture and renders
HTML with `templates/style.css`. That is printed to PDF in two passes (the first finds each heading's page from
the PDF bookmarks so the contents page shows page numbers) and merged with the covers by pypdf.

## Configuring

| To change | Edit |
|---|---|
| Chapter list/order, appendices, title, version, page size, TOC depth, covers | `manual.toml` |
| Typography, colours, callouts, tables, TOC look in the PDF | `templates/style.css` |
| Word styles used for new chapters | `templates/reference.docx` |
| Add a chapter | create a `.docx` in `chapters/` and add a `[[chapter]] docx = "..."` entry |

A chapter entry can also take a slice of a document (`from`/`until` on `##` heading names, with an `id` and
`title`) or fold other documents in as sections (`append = [...]`). `wiki = "x.md"` instead of `docx` still
builds a chapter directly from a wiki Markdown file.

## Notes

- **Word is the source of truth for the manual.** Don't also edit the wiki articles by hand for chapters that
  exist here, or the next export will overwrite those edits. Wiki pages that are not chapters (`Home.md`) stay
  hand-maintained in the wiki.
- `build/` and `.venv/` are git-ignored; `chapters/*.docx` are committed (binary, so Git cannot merge them -
  coordinate who edits which chapter).
