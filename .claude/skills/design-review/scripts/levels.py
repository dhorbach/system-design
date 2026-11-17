"""Show what each section of a depth-layered page contains at each level.

Usage:
  python3 levels.py SOURCE.html            per-section summary and structural flags
  python3 levels.py SOURCE.html --level N  the visible text a reader sees at depth N

An element's level is the highest data-l on it or any ancestor (1 when there is
none), which is how the page's CSS hides it. Sections are <section id=…>.
"""

import re
import sys
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
BLOCK = {"p", "li", "tr", "h2", "h3", "h4", "pre", "figcaption", "div", "table", "ul", "ol", "figure"}
COUNTED = {"table": "tables", "figure": "figures", "pre": "code blocks"}


class Levels(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []  # (tag, level, declared data-l or None)
        self.sections = []
        self.cur = None
        self.skip = 0  # inside script/style/svg

    def level(self):
        return self.stack[-1][1] if self.stack else 1

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "svg"):
            self.skip += 1
        if tag == "section" and a.get("id"):
            self.cur = {"id": a["id"], "toc": a.get("data-toc", a["id"]),
                        "more": {2: a.get("data-more2"), 3: a.get("data-more3")},
                        "text": {1: [], 2: [], 3: []}, "h3": {1: [], 2: [], 3: []},
                        "count": {n: dict.fromkeys(COUNTED.values(), 0) for n in (1, 2, 3)},
                        "flags": []}
            self.sections.append(self.cur)
        declared = int(a["data-l"]) if a.get("data-l", "").isdigit() else None
        lvl = max(self.level(), declared or 1)
        if self.cur and declared and declared < self.level():
            self.cur["flags"].append(f"inverted-nesting: data-l={declared} inside level {self.level()} never shows at depth {declared}")
        if self.cur and not self.skip:
            if tag in COUNTED:
                self.cur["count"][lvl][COUNTED[tag]] += 1
            if tag in BLOCK:
                self.cur["text"][lvl].append("\n")
            if tag == "h3":
                self.cur["h3"][lvl].append("")
        if tag not in VOID:
            self.stack.append((tag, lvl, declared))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag not in [t for t, _, _ in self.stack]:
            return
        while self.stack:
            t = self.stack.pop()[0]
            if t in ("script", "style", "svg"):
                self.skip -= 1
            if t == tag:
                break
        if tag == "section":
            self.cur = None

    def handle_data(self, data):
        if not self.cur or self.skip:
            return
        lvl = self.level()
        self.cur["text"][lvl].append(data)
        if any(t == "h3" for t, _, _ in self.stack) and self.cur["h3"][lvl]:
            self.cur["h3"][lvl][-1] += data


def clean(parts):
    lines = [re.sub(r"\s+", " ", l).strip() for l in "".join(parts).split("\n")]
    return [l for l in lines if l]


def words(parts):
    return len(" ".join(clean(parts)).split())


def summary(sections):
    for s in sections:
        w = {n: words(s["text"][n]) for n in (1, 2, 3)}
        total = sum(w.values()) or 1
        print(f"## {s['id']}: {s['toc']}")
        for n in (1, 2, 3):
            extras = ", ".join(f"{v} {k}" for k, v in s["count"][n].items() if v)
            h3 = "; ".join(h.strip() for h in s["h3"][n])
            line = f"  L{n}: {w[n]} words ({100 * w[n] // total}%)"
            if extras:
                line += f", {extras}"
            if h3:
                line += f" | h3: {h3}"
            if n > 1 and s["more"][n]:
                line += f' | more{n}: "{s["more"][n]}"'
            print(line)
        flags = list(s["flags"])
        if w[1] < 12:
            flags.append("no-level-1: fewer than 12 words visible at depth 1")
        if s["count"][1]["code blocks"]:
            flags.append("code-at-level-1: a code block is visible at depth 1")
        for n in (2, 3):
            has = w[n] > 0 or any(s["count"][n].values())
            if has and not s["more"][n]:
                flags.append(f"undeclared-level: level {n} content but no data-more{n}")
            if s["more"][n] and not has:
                flags.append(f"declared-empty: data-more{n} set but no level {n} content")
        for f in flags:
            print(f"  FLAG {f}")
        print()


def visible(sections, depth):
    """Text in reading order is not preserved across levels; print level by level."""
    for s in sections:
        print(f"## {s['id']}: {s['toc']}")
        for n in range(1, depth + 1):
            lines = clean(s["text"][n])
            if lines:
                print(f"[level {n}]")
                print("\n".join(lines))
        print()


def main(argv):
    parser = Levels()
    parser.feed(open(argv[0], encoding="utf-8").read())
    if "--level" in argv:
        visible(parser.sections, int(argv[argv.index("--level") + 1]))
    else:
        summary(parser.sections)


if __name__ == "__main__":
    main(sys.argv[1:])
