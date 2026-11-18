"""Keep only findings whose quote appears verbatim in the page's visible text.

Reader-facing attributes (depth descriptions, labels, titles, the page settings in
<meta content>) count as visible.

Usage: python3 check_quotes.py SOURCE.html FINDINGS.json > KEPT.json
FINDINGS.json is {"findings": [...]} as returned by the judge. Dropped findings
are listed on stderr.
"""

import json
import re
import sys
from html import unescape
from html.parser import HTMLParser


SHOWN_ATTRS = ("data-more2", "data-more3", "aria-label", "title", "alt", "content")


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        for name, value in attrs:
            if name in SHOWN_ATTRS and value:
                self.parts.append(value)

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def norm(s):
    s = unescape(s).replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def main(source, findings):
    parser = Text()
    parser.feed(open(source, encoding="utf-8").read())
    text = norm(" ".join(parser.parts))
    # Text split across inline elements loses its spaces differently; compare without spaces too.
    squashed = text.replace(" ", "")
    data = json.load(open(findings, encoding="utf-8"))
    kept = []
    for f in data["findings"]:
        q = norm(f.get("quote", ""))
        if q and (q in text or q.replace(" ", "") in squashed):
            kept.append(f)
        else:
            print(f"dropped (quote not found): {f.get('title')!r}: {f.get('quote')!r}", file=sys.stderr)
    json.dump({"findings": kept}, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:3])
