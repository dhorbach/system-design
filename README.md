# System design articles

Page sources live in `pages/`. Each file is a `<head>` and a `<body>` fragment
holding content only. The build wraps every page in `templates/page.html`, which
owns the document, the fonts, the shared tokens (`static/assets/base.css`) and the
Google Tag Manager and Cloudflare Analytics scripts. Edit tracking settings there.
Google Analytics tags are configured separately inside Google Tag Manager.

## Guides

A system design guide names the guide layout in its head
(`<meta name="layout" content="guide">`). The build then places it into
`templates/guide.html` first. What is shared between guides:

| File | Holds |
|---|---|
| `templates/guide.html` | Top bar, depth switch, contents, hero |
| `static/assets/guide.css` | Styles of the shell and of every shared component |
| `static/assets/guide.js` | Depth levels, contents, hover definitions, requirement tags, step-through figures, code colouring |

A guide page holds its title and description, its component colours, the
component map, its sections, its glossary, and the styles and script of demos
that only it has. `pages/distributed-job-scheduler.html` is the example.

To add a guide, use the `design-page` skill (`.claude/skills/design-page/`). It
works in stages (scope, model, design, draft, depth, pre-review) and stops after
each one at a design board artifact, where you answer its questions (three options
each) and approve, change or drop each part before it goes on. Work in progress
lives in `drafts/<slug>/` (gitignored). The skill has the starter page, the format
reference and a check
(`python3 .claude/skills/design-page/scripts/check_page.py pages/NAME.html`).
The `design-review` skill reviews a finished page. Then add the page's dated card
to `pages/index.html`.

Do not copy shared styles, scripts or analytics into page sources. To change the
look or behaviour of every guide, edit the shared files above. Subdirectories
within `pages/` are preserved; shared files are linked relative to each page.

## Layout slots

A layout is a `<head>` and `<body>` fragment in `templates/` with slots:
`{{head}}` and `{{body}}` (the page's own), `{{title}}`, `{{name}}` or
`{{name|default}}` (filled from `<meta name="name" content="…">` in the page's
head or `<template data-slot="name">…</template>` in its body),
`{{asset:assets/file.css}}` (the address of `static/assets/file.css` from the
page, with a content hash so browsers pick up new versions) and `{{root}}`.

## Build and preview

Python 3, no packages to install:

```sh
python3 scripts/build.py
python3 -m http.server 8000 --directory _site
```

Open http://localhost:8000. `_site/` is generated and should not be edited.
Put images and other unchanged assets in `static/`; they are copied to the output
root. The Google site-verification file lives there and remains unchanged.

GitHub Pages builds and validates the site before deploying only `_site/`.
Validation fails if any visitor HTML page is missing either analytics script,
has duplicate scripts, or uses the wrong tracking IDs. Exact Google verification
documents are exempt because they are not visitor pages.

Run build checks with:

```sh
python3 -m unittest discover -s scripts -p 'test_*.py'
```
