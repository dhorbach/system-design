#!/usr/bin/env python3
"""Fill the report template from the verdicts and the notes written about them.

    report.py verdicts.json notes.json out.html [--template path] [--standalone]

verdicts.json comes from `verdict.py judge --out`. notes.json is written by hand
and holds what the numbers cannot say for themselves:

    {"lead": "two sentences: what held and what gave way first (HTML allowed)",
     "findings": [{"title": "…", "body": "<p>…</p>", "claims": ["NFR2"]}],
     "curves": [{"title": "…", "x": "Offered rate, runs/s", "y": "99th percentile delay, ms",
                 "points": [[50, 210], [100, 240]], "fit": [[1, 300], [16, 1500]], "fit_label": "fit",
                 "target": 1000, "target_label": "NFR2: 1 s", "note": "…"}],
     "runs": [{"scenario": "steady", "what": "200 runs/s for 5 min on the aged dataset", "runs": 3}],
     "reproduce": "cd bench/<slug>\\n./run.sh calibration\\n…"}

Every key is optional. Keys in notes.json win over the same keys in verdicts.json.

By default the output is the fragment an artifact host wraps in a document. With
--standalone it is a complete HTML document that opens from disk in a browser.
"""
import json
import os
import re
import sys


def main():
    args = sys.argv[1:]
    template = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "report.html")
    if "--template" in args:
        i = args.index("--template")
        template = args[i + 1]
        del args[i:i + 2]
    standalone = "--standalone" in args
    if standalone:
        args.remove("--standalone")
    if len(args) != 3:
        print(__doc__)
        return 2
    with open(args[0]) as f:
        data = json.load(f)
    with open(args[1]) as f:
        data.update(json.load(f))
    with open(template) as f:
        page = f.read()
    blob = json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/")
    page, n = re.subn(r'(<script type="application/json" id="report-data">).*?(</script>)',
                      lambda m: m.group(1) + "\n" + blob + "\n" + m.group(2), page, count=1, flags=re.S)
    if n != 1:
        print("template has no report-data block", file=sys.stderr)
        return 2
    title = (data.get("design", {}).get("title") or "Bench") + " bench"
    page = re.sub(r"<title>.*?</title>", "<title>" + title.replace("&", "&amp;").replace("<", "&lt;") + "</title>", page, count=1)
    if standalone:
        page = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1">\n<style>body{margin:0}</style>\n'
                '</head>\n<body>\n' + page + '\n</body>\n</html>\n')
    with open(args[2], "w") as f:
        f.write(page)
    print(f"wrote {args[2]}: {len(data.get('claims', []))} claims, {sum(len(c.get('runs', [])) for c in data.get('claims', []))} runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
