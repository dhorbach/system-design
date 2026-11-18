import shutil
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import build

GUIDE = '''<head>
<meta name="layout" content="guide">
<title>Building a "thing"</title>
<meta name="short-title" content="Thing">
<meta name="description" content="About the thing.">
<meta name="depth-3" content="SQL and code.">
<style>.k-a{--k:var(--teal)}</style>
</head>
<body>
<template data-slot="map">
  <svg class="minimap"></svg>
</template>
<section id="overview" data-toc="Problem"><p>A Helm value looks like {{body}} or {{asset:x}}.</p></section>
</body>'''


@contextmanager
def site(pages):
    """A copy of the real templates and assets with the given page sources."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copytree(build.ROOT / "templates", root / "templates")
        shutil.copytree(build.ROOT / "static" / "assets", root / "static" / "assets")
        for name, source in pages.items():
            (root / "pages" / name).parent.mkdir(parents=True, exist_ok=True)
            (root / "pages" / name).write_text(source)
        with patch.object(build, "ROOT", root), patch.object(build, "OUTPUT", root / "_site"):
            yield root


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.layout = (build.ROOT / "templates/page.html").read_text()
        self.plain = '<head><title>Example</title></head><body><h1>Example</h1></body>'

    def test_shared_layout_has_both_trackers(self):
        build.validate_page(self.layout)

    def test_missing_or_duplicate_tracker_fails(self):
        for url in (build.GTM_URL, build.CF_URL):
            with self.subTest(url=url, case="missing"):
                with self.assertRaises(ValueError):
                    build.validate_page(self.layout.replace(url, "https://example.com/script.js"))
            with self.subTest(url=url, case="duplicate"):
                with self.assertRaises(ValueError):
                    build.validate_page(self.layout + f'<script src="{url}"></script>')

    def test_wrong_cloudflare_token_fails(self):
        with self.assertRaises(ValueError):
            build.validate_page(self.layout.replace(build.CF_TOKEN, "wrong-token"))

    def test_new_pages_inherit_tracking_and_static_html_is_checked(self):
        with site({"index.html": self.plain, "new-article.html": self.plain}) as root:
            verification = "google123abc.html"
            (root / "static" / verification).write_text(f"google-site-verification: {verification}")
            build.build()
            build.validate_page((root / "_site/new-article.html").read_text())
            self.assertEqual((root / "static" / verification).read_bytes(), (root / "_site" / verification).read_bytes())
            (root / "static/untracked.html").write_text('<html><body>Missing trackers</body></html>')
            with self.assertRaisesRegex(ValueError, "untracked.html"):
                build.build()

    def test_guide_layout_places_the_page_in_the_shared_shell(self):
        with site({"index.html": self.plain, "thing.html": GUIDE, "deep/thing.html": GUIDE}) as root:
            build.build()
            page = (root / "_site/thing.html").read_text()
            build.validate_page(page)
            # the page's settings fill the shell
            self.assertIn('<h1>Building a &quot;thing&quot;</h1>', page)
            self.assertIn('aria-label="Back to top: Thing">Thing</a>', page)
            self.assertIn("<span>SQL and code.</span>", page)
            self.assertIn("<span>How each part works, with every term explained.</span>", page)  # layout default
            self.assertRegex(page, r'(?s)<nav class="side".*<svg class="minimap"></svg>.*</nav>\s*<main id="main">.*<section id="overview"')
            self.assertNotIn("<template", page)
            # settings the layout used are dropped from the head; the rest stays, after the shared styles
            for name in ("layout", "short-title", "depth-3"):
                self.assertNotIn(f'name="{name}"', page)
            self.assertIn('<meta name="description" content="About the thing.">', page)
            self.assertLess(page.index("assets/guide.css"), page.index(".k-a{--k:var(--teal)}"))
            # slot-like text in the article is left alone
            self.assertIn("looks like {{body}} or {{asset:x}}.", page)
            # shared files are linked with a content hash, relative to the page
            self.assertRegex(page, r'href="assets/base\.css\?v=[0-9a-f]{8}"')
            self.assertRegex(page, r'<script defer src="assets/guide\.js\?v=[0-9a-f]{8}">')
            self.assertRegex((root / "_site/deep/thing.html").read_text(), r'href="\.\./assets/guide\.css\?v=[0-9a-f]{8}"')
            self.assertTrue((root / "_site/assets/guide.js").is_file())

    def test_asset_address_changes_with_the_file(self):
        with site({"index.html": self.plain}) as root:
            before = build.render(root / "pages/index.html")
            (root / "static/assets/base.css").write_text("body{}")
            self.assertNotEqual(before, build.render(root / "pages/index.html"))

    def test_layout_problems_name_the_page_and_the_cause(self):
        cases = {
            "depth-3": GUIDE.replace('<meta name="depth-3" content="SQL and code.">\n', ""),
            "map": GUIDE.replace('data-slot="map"', 'data-slot="other"'),
            "unknown layout 'nope'": GUIDE.replace('content="guide"', 'content="nope"'),
            "fragment": "<main>no head or body</main>",
        }
        for expected, source in cases.items():
            with self.subTest(expected=expected), site({"index.html": self.plain, "broken.html": source}):
                with self.assertRaisesRegex(ValueError, rf"pages/broken\.html: .*{expected}"):
                    build.build()


if __name__ == "__main__":
    unittest.main()
