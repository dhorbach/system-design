"""Build every page through the shared layouts, then validate the output.

A page source is a <head> and a <body> fragment. templates/page.html wraps every
page: it owns the document, the fonts, base.css and the analytics scripts.

A page that names a layout (<meta name="layout" content="guide">) is first placed
into templates/<layout>.html. A layout is itself a <head> and <body> fragment with
slots written as {{name}} or {{name|default}}:

  {{head}}, {{body}}   the page's own head and body
  {{title}}            the text of the page's <title>
  {{any-name}}         <meta name="any-name" content="…"> in the page's head, or
                       <template data-slot="any-name">…</template> in its body
  {{asset:path}}       the address of static/<path> from this page, with a content
                       hash so browsers pick up a new version
  {{root}}             the relative path from this page to the site root
"""

import hashlib
import json
import re
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "_site"
DEV_OUTPUT = ROOT / "_dev"
ANALYTICS = re.compile(
    r"<script[^>]*googletagmanager\.com[^>]*></script>\s*<script>.*?dataLayer.*?</script>\s*"
    r"|<!-- Cloudflare Web Analytics -->.*?<!-- End Cloudflare Web Analytics -->\s*",
    re.S,
)
GTM_URL = "https://www.googletagmanager.com/gtm.js?id=GTM-N4NC3S3Q"
CF_URL = "https://static.cloudflareinsights.com/beacon.min.js"
CF_TOKEN = "42ea943f44b14746994f7cfa917cc3ab"

FRAGMENT = re.compile(r"\s*<head>(.*?)</head>\s*<body>(.*?)</body>\s*", re.S)
SLOT = re.compile(r"\{\{([a-z0-9:./_-]+)(?:\|([^{}]*))?\}\}")
META = re.compile(r'<meta\s+name="([^"]+)"\s+content="([^"]*)"\s*/?>[ \t]*\n?')
TITLE = re.compile(r"<title>(.*?)</title>", re.S)
PAGE_SLOT = re.compile(r'<template\s+data-slot="([a-z0-9-]+)">(.*?)</template>[ \t]*\n?', re.S)


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


def split(source, what):
    parts = FRAGMENT.fullmatch(source)
    if not parts:
        raise ValueError(f"{what} must be a <head> and a <body> fragment")
    return parts.group(1).strip(), parts.group(2).strip()


def fill(template, values, root):
    """Fill a template's slots in one pass, so {{…}} in article text stays untouched."""
    def value(match):
        name, default = match.group(1), match.group(2)
        if name == "root":
            return root
        if name.startswith("asset:"):
            asset = ROOT / "static" / name[6:]
            if not asset.is_file():
                raise ValueError(f"missing asset static/{name[6:]}")
            return f"{root}{name[6:]}?v={hashlib.sha256(asset.read_bytes()).hexdigest()[:8]}"
        if name in values:
            return values[name]
        if default is not None:
            return default
        raise ValueError(f'nothing fills {{{{{name}}}}}: add <meta name="{name}" content="…"> '
                         f'or <template data-slot="{name}">…</template> to the page')
    return SLOT.sub(value, template)


def render(page):
    """Return the finished document for one page source."""
    relative = page.relative_to(ROOT / "pages")
    root = "../" * (len(relative.parts) - 1)
    head, body = split(page.read_text(), "the page")
    meta = dict(META.findall(head))
    if "layout" in meta:
        template = ROOT / "templates" / f"{meta['layout']}.html"
        if meta["layout"] == "page" or not template.is_file():
            raise ValueError(f"unknown layout {meta['layout']!r}")
        layout_head, layout_body = split(template.read_text(), f"templates/{template.name}")
        title = TITLE.search(head)
        values = dict(meta, title=title.group(1).strip().replace('"', "&quot;") if title else "")
        values.update((name, content.strip()) for name, content in PAGE_SLOT.findall(body))
        # Settings the layout has placed are not repeated in the document head.
        used = {"layout"} | {name for name, _ in SLOT.findall(layout_head + layout_body)}
        values["head"] = META.sub(lambda m: "" if m.group(1) in used else m.group(0), head).strip()
        values["body"] = PAGE_SLOT.sub("", body).strip()
        head, body = fill(layout_head, values, root), fill(layout_body, values, root)
    return fill((ROOT / "templates/page.html").read_text(), {"head": head, "body": body}, root)


def build(dev=False):
    """Build into _site and validate. With dev, build into _dev without analytics."""
    output = DEV_OUTPUT if dev else OUTPUT
    layout = (ROOT / "templates/page.html").read_text()
    for slot in ("{{head}}", "{{body}}"):
        if layout.count(slot) != 1:
            raise ValueError(f"Shared layout must contain exactly one {slot}")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir()
    shutil.copytree(ROOT / "static", output, dirs_exist_ok=True)
    pages = sorted((ROOT / "pages").rglob("*.html"))
    if not pages:
        raise ValueError("No pages found")
    for page in pages:
        try:
            source = render(page)
        except ValueError as error:
            raise ValueError(f"{page.relative_to(ROOT)}: {error}") from error
        destination = output / page.relative_to(ROOT / "pages")
        if destination.exists():
            raise ValueError(f"Page conflicts with a static file: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(ANALYTICS.sub("", source) if dev else source)
    for page in () if dev else output.rglob("*.html"):
        source = page.read_text()
        # Search Console verification documents are tokens, not visitor pages.
        if re.fullmatch(r"google[a-f0-9]+\.html", page.name) and source.strip() == f"google-site-verification: {page.name}":
            continue
        try:
            validate_page(source)
        except (ValueError, TypeError) as error:
            raise ValueError(f"{page.relative_to(output)}: {error}") from error
    if not (output / "index.html").is_file():
        raise ValueError("Missing index.html entry point")
    print(f"Built and validated {len(pages)} pages in {output}")


if __name__ == "__main__":
    build(dev="--dev" in sys.argv[1:])
