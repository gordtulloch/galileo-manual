# Galileo User Manual

Source and build tooling for the Galileo manual shipped with each release. Chapters come primarily from the
[Galileo wiki](../Galileo.wiki), with screenshots from the Galileo repo, plus any manual-only chapters and
graphics kept here. The output is a single PDF: front cover, title page, table of contents with page numbers,
chapters (footer with title/version/page number), rear cover, and PDF bookmarks.

## Build (Windows)

```powershell
.\build.ps1                      # -> build\Galileo-Manual.pdf
.\build.ps1 --version 1.0.0      # override the version on the title page
.\build.ps1 --only 06,07         # just those chapters, for quick layout iteration
.\build.ps1 --html-only          # write build\manual.html only (open in a browser)
.\build.ps1 --refresh-images     # re-download cached remote images
```

Requirements: Python 3.11+ and Microsoft Edge (included with Windows 11) or Google Chrome. The first run creates
`.venv` and installs `markdown`, `playwright` and `pypdf`. Playwright drives the **installed** Edge/Chrome, so
no browser download is needed.

Expected sibling checkouts (paths in `manual.toml`): `../Galileo.wiki` and `../Galileo`.

## How it works

`build_manual.py` converts each chapter's Markdown to HTML, namespaces heading ids per chapter, rewrites wiki
cross-links (`06.-Imaging#taking-an-exposure`) into in-document links, drops wiki-only furniture (per-article
"Contents" lists, `---` rules), and resolves screenshots locally. Images referenced as
`raw.githubusercontent.com/gordtulloch/Galileo/main/...` are taken from `images/` first, then the Galileo
checkout, then a download cache in `build/image-cache`. A lone image in a paragraph becomes a figure whose
alt text is the printed caption. The HTML is printed to PDF in two passes (the first finds each heading's page
via the PDF bookmarks so the table of contents can show page numbers), then merged with the covers by pypdf.

## Customising

| To change | Edit |
|---|---|
| Chapter list/order, title, version, page size, TOC depth, covers | `manual.toml` |
| Typography, colours, callouts, tables, TOC look | `templates/style.css` |
| Replace a screenshot, or add a diagram | drop a same-named file in `images/` (see `images/README.md`) |
| Add a manual-only chapter | add Markdown under `content/` and a `[[chapter]] file = "content/x.md"` entry |
| Make a chapter an appendix | `appendix = true` in its `[[chapter]]` entry |

Chapters whose wiki article has a different title than you want in print can set `title = "..."`.

## Notes

- Wiki text is authoritative; fix content in `../Galileo.wiki` rather than patching it here, so the wiki and
  manual don't drift. Manual-only prose and graphics live in this repo.
- Wiki links to pages that are not in the manual (e.g. `Home`) are printed as plain text.
- `build/` and `.venv/` are git-ignored.
