import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.layout = (build.ROOT / "templates/page.html").read_text()

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
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ("pages", "templates", "static"):
                (root / folder).mkdir()
            (root / "templates/page.html").write_text(self.layout)
            fragment = '<head><title>Example</title></head><body><h1>Example</h1></body>'
            for name in ("index.html", "new-article.html"):
                (root / "pages" / name).write_text(fragment)
            verification = "google123abc.html"
            (root / "static" / verification).write_text(f"google-site-verification: {verification}")
            with patch.object(build, "ROOT", root), patch.object(build, "OUTPUT", root / "_site"):
                build.build()
                build.validate_page((root / "_site/new-article.html").read_text())
                self.assertEqual((root / "static" / verification).read_bytes(), (root / "_site" / verification).read_bytes())
                (root / "static/untracked.html").write_text('<html><body>Missing trackers</body></html>')
                with self.assertRaisesRegex(ValueError, "untracked.html"):
                    build.build()


if __name__ == "__main__":
    unittest.main()
