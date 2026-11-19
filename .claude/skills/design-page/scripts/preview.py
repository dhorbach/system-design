"""Build a page without analytics and write it as one self-contained file for an artifact.

Usage: python3 .claude/skills/design-page/scripts/preview.py pages/<slug>.html <out.html>

Runs the dev build (scripts/build.py --dev, no analytics tags), takes
_dev/<slug>.html and inlines its local stylesheets and scripts, so the result can be
published with the Artifact tool as a single page. The reader switches depth with
the page's own control.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LINK = re.compile(r'<link rel="stylesheet" href="(assets/[^"?]+)(?:\?[^"]*)?">')
SCRIPT = re.compile(r'<script( defer)? src="(assets/[^"?]+)(?:\?[^"]*)?"></script>')


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    source, out = Path(argv[0]), Path(argv[1])
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build.py"), "--dev"], check=True, cwd=ROOT,
                   stdout=subprocess.DEVNULL)
    built = ROOT / "_dev" / Path(source).relative_to("pages") if source.parts[0] == "pages" else None
    if not built or not built.exists():
        sys.exit(f"no built page for {source} in _dev/")
    page = built.read_text()

    def css(m):
        return "<style>\n" + (ROOT / "_dev" / m.group(1)).read_text().replace("</style", "<\\/style") + "\n</style>"

    def js(m):
        code = (ROOT / "_dev" / m.group(2)).read_text().replace("</script", "<\\/script")
        if m.group(1):  # keep defer semantics: run after the document is parsed
            code = "document.addEventListener('DOMContentLoaded',function(){\n" + code + "\n});"
        return "<script>\n" + code + "\n</script>"

    page = LINK.sub(css, page)
    page = SCRIPT.sub(js, page)
    left = re.findall(r'(?:href|src)="(assets/[^"]+)"', page)
    if left:
        sys.exit(f"local assets left un-inlined: {left}")
    if re.search(r"googletagmanager|cloudflareinsights", page):
        sys.exit("analytics tags found in the preview; refusing to write it")
    out.write_text(page)
    print(f"wrote {out} ({len(page) // 1024} KiB)")


if __name__ == "__main__":
    main(sys.argv[1:])
