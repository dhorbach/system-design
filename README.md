# System design articles

Page sources live in `pages/`. Each file contains a `<head>` and a `<body>`
fragment. The build wraps them in `templates/page.html`, which owns the shared
Google Tag Manager and Cloudflare Analytics scripts. Edit tracking settings there.
Google Analytics tags are configured separately inside Google Tag Manager.

To add an article, create `pages/article-name.html` using an existing page as a
starting point, then add its dated link to `pages/index.html`. Do not copy analytics
scripts into page sources. Subdirectories within `pages/` are preserved; use links
relative to the destination page.

Build and preview with Python 3 (no packages to install):

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
