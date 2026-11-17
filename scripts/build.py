"""Build every page through the shared layout, then validate the output."""

import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "_site"
GTM_URL = "https://www.googletagmanager.com/gtm.js?id=GTM-N4NC3S3Q"
CF_URL = "https://static.cloudflareinsights.com/beacon.min.js"
CF_TOKEN = "42ea943f44b14746994f7cfa917cc3ab"


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.scripts.append(dict(attrs))


def validate_page(source):
    parser = Scripts()
    parser.feed(source)
    google = [s for s in parser.scripts if s.get("src", "").startswith(
        "https://www.googletagmanager.com/"
    )]
    cloudflare = [s for s in parser.scripts if s.get("src", "").startswith(
        "https://static.cloudflareinsights.com/"
    )]
    if len(google) != 1 or google[0].get("src") != GTM_URL or "async" not in google[0]:
        raise ValueError("Expected exactly one async Google Tag Manager script")
    if len(cloudflare) != 1 or cloudflare[0].get("src") != CF_URL:
        raise ValueError("Expected exactly one Cloudflare Analytics script")
    if json.loads(cloudflare[0].get("data-cf-beacon", "{}" )).get("token") != CF_TOKEN:
        raise ValueError("Incorrect Cloudflare Analytics token")
    if "window.dataLayer = window.dataLayer || [];" not in source or "gtag('js', new Date());" not in source:
        raise ValueError("Missing Google tracking initialization")


def build():
    layout = (ROOT / "templates/page.html").read_text()
    for slot in ("{{head}}", "{{body}}"):
        if layout.count(slot) != 1:
            raise ValueError(f"Shared layout must contain exactly one {slot}")
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir()
    shutil.copytree(ROOT / "static", OUTPUT, dirs_exist_ok=True)
    pages = sorted((ROOT / "pages").rglob("*.html"))
    if not pages:
        raise ValueError("No pages found")
    for page in pages:
        parts = re.fullmatch(r"\s*<head>(.*?)</head>\s*<body>(.*?)</body>\s*", page.read_text(), re.S)
        if not parts:
            raise ValueError(f"{page}: expected a <head> and <body> fragment")
        # Substitute in one pass so placeholders in article text stay untouched.
        source = re.sub(r"\{\{(head|body)\}\}", lambda m: parts.group(1 if m[1] == "head" else 2).strip(), layout)
        destination = OUTPUT / page.relative_to(ROOT / "pages")
        if destination.exists():
            raise ValueError(f"Page conflicts with a static file: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source)
    for page in OUTPUT.rglob("*.html"):
        source = page.read_text()
        # Search Console verification documents are tokens, not visitor pages.
        if re.fullmatch(r"google[a-f0-9]+\.html", page.name) and source.strip() == f"google-site-verification: {page.name}":
            continue
        try:
            validate_page(source)
        except (ValueError, TypeError) as error:
            raise ValueError(f"{page.relative_to(OUTPUT)}: {error}") from error
    if not (OUTPUT / "index.html").is_file():
        raise ValueError("Missing index.html entry point")
    print(f"Built and validated {len(pages)} pages in {OUTPUT}")


if __name__ == "__main__":
    build()
