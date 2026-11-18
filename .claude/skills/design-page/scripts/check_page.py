"""Check a guide page source against the format the shared layout and the design review expect.

Usage:
  python3 check_page.py pages/NAME.html            errors and warnings
  python3 check_page.py pages/NAME.html --numbers  every large number and the sections that use it

Errors are things that are broken or that the review reports from structure alone
(a dead link, a requirement nothing delivers, a heading with nothing under it).
Warnings are things to read and judge. Exit status is 1 when there are errors.
"""

import importlib.util
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[4]
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
LAYOUT_IDS = {"main", "menu", "side", "toc", "scrim", "gseg", "pick", "prog", "tip", "ah", "ahb"}
REQUIRED = ["overview", "terms", "requirements", "estimates", "system", "reading"]
HUES = {"teal", "indigo", "amber", "rose", "violet", "green", "slate"}
LANGS = {"go", "sql", "json", "none"}
SINGLE_LEVEL = {"overview", "system", "reading"}  # sections that may be all level 1
# Words that name a mechanism, not a guarantee (rubrics/requirements.md, check 1).
MECHANISMS = (r"leases?|epochs?|fenc\w+|outbox\w*|idempotency keys?|tokens?|caches?|cached|index(?:es)?|"
              r"SQL|poll\w*|lookahead|heartbeats?|shards?|sharding|partitions?|replicas?|consensus|"
              r"Kafka|Redis|Postgres\w*|MySQL|Cassandra|DynamoDB|etcd|ZooKeeper|S3|SQS|RabbitMQ|Raft|Paxos|"
              r"B-trees?|hash(?:es|ing)?|bloom filters?|WAL|write-ahead log|CDN|load balancers?|websockets?|gRPC")
SIZES = {"bytes": 1, "byte": 1, "B": 1, "KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12, "PB": 1e15}


class Node:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent, self.children = tag, attrs, parent, []

    @property
    def classes(self):
        return set((self.attrs.get("class") or "").split())

    def walk(self):
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.walk()

    def all(self, tag=None, cls=None):
        return [n for n in self.walk() if (tag is None or n.tag == tag) and (cls is None or cls in n.classes)]

    def text(self, skip=("script", "style")):
        parts = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag not in skip:
                parts.append("\n" if child.tag == "br" else child.text(skip))
        return "".join(parts)

    def up(self, test):
        node = self.parent
        while node is not None and not test(node):
            node = node.parent
        return node

    @property
    def level(self):
        node, level = self, 1
        while node is not None:
            value = node.attrs.get("data-l", "")
            level = max(level, int(value) if value.isdigit() else 1)
            node = node.parent
        return level


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.cur = Node("root", {}, None)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        node = self.cur
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self.cur = node.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def squash(text):
    return re.sub(r"\s+", " ", text).strip()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Check:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.source = self.path.read_text(encoding="utf-8")
        self.errors, self.warnings = [], []
        tree = Tree()
        tree.feed(self.source)
        self.root = tree.root
        self.sections = [n for n in self.root.all("section") if n.attrs.get("id")]
        self.by_id = {s.attrs["id"]: s for s in self.sections}

    def error(self, where, message):
        self.errors.append(f"{where}: {message}")

    def warn(self, where, message):
        self.warnings.append(f"{where}: {message}")

    # -- page settings and what the layout owns ---------------------------------
    def settings(self):
        head = (self.root.all("head") or [self.root])[0]
        meta = {m.attrs.get("name"): m.attrs.get("content", "") for m in head.all("meta")}
        if meta.get("layout") != "guide":
            self.error("head", 'missing <meta name="layout" content="guide">')
        if not head.all("title") or not squash(head.all("title")[0].text()):
            self.error("head", "missing <title>")
        for name in ("short-title", "description", "depth-3"):
            if not meta.get(name):
                self.error("head", f'missing <meta name="{name}" content="…">')
        if len(meta.get("description", "")) > 200:
            self.warn("head", f"description is {len(meta['description'])} characters; search results cut it near 160")
        for owned, why in (("charset", "the charset"), ("viewport", "the viewport")):
            if owned in meta or any(owned in m.attrs for m in head.all("meta")):
                self.error("head", f"templates/page.html already sets {why}; remove it from the page")
        if head.all("link"):
            self.error("head", "no <link> in a page: fonts, base.css and guide.css come from the templates")
        for node in self.root.walk():
            if node.tag in ("header", "main", "nav", "footer", "h1") and not node.up(lambda n: n.tag == "svg"):
                self.error("body", f"<{node.tag}> belongs to templates/guide.html; a page holds only sections, the map, the glossary and its own script")
            if node.tag == "script" and re.search(r"googletagmanager|cloudflareinsights", node.attrs.get("src", "") + node.text(())):
                self.error("body", "analytics scripts live in templates/page.html only")
            if node.tag == "script" and node.attrs.get("src"):
                self.error("body", f"external script {node.attrs['src']}: shared behaviour goes in static/assets/guide.js")
        scripts = [n for n in self.root.all("script") if not n.attrs.get("src") and n.attrs.get("type", "") in ("", "text/javascript", "module")]
        for script in scripts:
            if "guide:ready" not in script.text(()):
                self.warn("script", "start page demos from the guide:ready event so they run after the shared chrome is built")

    def styles(self):
        css = "\n".join(s.text(()) for s in self.root.all("style"))
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        self.kinds = set(re.findall(r"\.k-([a-z0-9-]+)\s*\{", css))
        used = {c[2:] for n in self.root.walk() for c in n.classes if c.startswith("k-")}
        for kind in sorted(used - self.kinds):
            self.error("style", f"class k-{kind} is used but the page's <style> has no .k-{kind}{{--k:…}} rule")
        for name, value in re.findall(r"\.k-([a-z0-9-]+)\s*\{\s*--k:\s*([^;}]+)", css):
            hue = re.fullmatch(r"var\(--([a-z]+)\)", value.strip())
            alias = hue and re.search(r"--%s:\s*var\(--([a-z]+)\)" % re.escape(hue.group(1)), css)
            final = alias.group(1) if alias else (hue.group(1) if hue else None)
            if final not in HUES:
                self.warn("style", f".k-{name} should take one of the shared hues ({', '.join(sorted(HUES))}), which have light and dark values")
        if re.search(r"#[0-9a-fA-F]{3,8}\b", css):
            self.warn("style", "hard-coded colour in the page's <style>: use the shared tokens so dark mode keeps working")
        shared = (REPO / "static/assets/guide.css").read_text() + (REPO / "static/assets/base.css").read_text()
        shared = re.sub(r"/\*.*?\*/", "", shared, flags=re.S)
        selectors = lambda text: {squash(s) for block in re.findall(r"([^{}]+)\{", text) for s in block.split(",") if squash(s) and not squash(s).startswith("@")}
        for selector in sorted((selectors(css) & selectors(shared)) - {":root"}):
            self.warn("style", f"'{selector}' is already styled in the shared CSS; change it there, or use a page-only class")

    # -- map, sections, links ----------------------------------------------------
    def structure(self):
        slots = [t for t in self.root.all("template") if t.attrs.get("data-slot") == "map"]
        nodes = slots[0].all(cls="n") if slots else []
        if not slots or not slots[0].all("svg", "minimap"):
            self.error("map", 'missing <template data-slot="map"> holding <svg class="minimap">')
        ids = [s.attrs["id"] for s in self.sections]
        map_nodes = set()
        for node in nodes:
            name = node.attrs.get("data-node")
            map_nodes.add(name)
            if not name or not node.attrs.get("aria-label") or not any(c.startswith("k-") for c in node.classes):
                self.error("map", f"map node {name or '?'} needs data-node, a k-* class and an aria-label")
            if node.attrs.get("data-go") not in ids:
                self.error("map", f"map node {name} points at data-go=\"{node.attrs.get('data-go')}\", which is not a section id")
        lit = set()
        for i, section in enumerate(self.sections):
            sid = section.attrs["id"]
            if not re.fullmatch(r"[a-z][a-z0-9-]*", sid):
                self.error(sid, "section ids are lower-case words joined by hyphens")
            if not section.attrs.get("data-toc"):
                self.error(sid, "missing data-toc (the name shown in the contents list)")
            head = [c for c in section.children if isinstance(c, Node)][:1]
            if not head or "sh" not in head[0].classes or not head[0].all("h2"):
                self.error(sid, 'a section starts with <div class="sh"><h2>…</h2></div>')
            if section.attrs.get("data-num") and not section.all("span", "num"):
                self.error(sid, 'data-num is set but the heading has no <span class="num">')
            if section.attrs.get("data-num") and not any(c.startswith("k-") for c in section.classes):
                self.error(sid, "a numbered component section needs its k-* class")
            wanted = set((section.attrs.get("data-nodes") or "").split())
            lit |= wanted
            for missing in sorted(wanted - map_nodes):
                self.error(sid, f'data-nodes names "{missing}", which is not a data-node in the map')
            if "data-nodes" not in section.attrs:
                self.error(sid, 'missing data-nodes (use data-nodes="" when no component should light up)')
        for unused in sorted(n for n in map_nodes - lit if n):
            self.warn("map", f'no section lights up map node "{unused}"')
        if ids and "data-group" not in self.sections[0].attrs:
            self.warn(ids[0], "the first section should start a contents group (data-group)")
        order = [i for i in ids if i in REQUIRED]
        for missing in [r for r in REQUIRED if r not in ids]:
            self.error("sections", f'missing section id="{missing}"')
        if order != [r for r in REQUIRED if r in ids]:
            self.error("sections", f"expected the order {', '.join(REQUIRED)} (components and cross-cutting sections go between system and reading)")
        if "reading" in self.by_id and not self.by_id["reading"].attrs.get("data-ref"):
            self.error("reading", 'the references section needs data-ref="1" so it is left out of the reading time')

        all_ids = {}
        for node in self.root.walk():
            if "id" in node.attrs:
                all_ids.setdefault(node.attrs["id"], []).append(node)
        for name, found in all_ids.items():
            if len(found) > 1:
                self.error("ids", f'id="{name}" is used {len(found)} times')
            if name in LAYOUT_IDS:
                self.error("ids", f'id="{name}" is taken by the shared layout')
        generated = set()
        for ul in self.root.all("ul"):
            if ul.attrs.get("data-reqs"):
                items = [c for c in ul.children if isinstance(c, Node) and c.tag == "li"]
                generated |= {f"{ul.attrs['data-reqs'].lower()}{i + 1}" for i in range(len(items))}
        for section in self.sections:
            generated |= {f"{section.attrs['id']}-{i + 1}" for i in range(len(section.all("h3")))}
        known = set(all_ids) | generated | LAYOUT_IDS
        for a in self.root.all("a"):
            href = a.attrs.get("href", "")
            section = a.up(lambda n: n.tag == "section")
            where = section.attrs.get("id", "?") if section else "page"
            if href.startswith("#") and href[1:] not in known:
                self.error(where, f'link to "{href}" has no target')
            if href.startswith("http") and a.attrs.get("target") != "_blank":
                self.warn(where, f"external link {href} should open in a new tab (target=\"_blank\" rel=\"noopener\")")

    # -- depth levels ------------------------------------------------------------
    def depth(self):
        levels = load(HERE.parents[2] / "design-review/scripts/levels.py", "levels")
        parser = levels.Levels()
        parser.feed(self.source)
        for s in parser.sections:
            words = {n: levels.words(s["text"][n]) for n in (1, 2, 3)}
            for flag in s["flags"]:
                self.error(s["id"], flag)
            if words[1] < 12:
                self.error(s["id"], "fewer than 12 words are visible at depth 1")
            if s["count"][1]["code blocks"]:
                self.error(s["id"], "a code block is visible at depth 1")
            for n in (2, 3):
                has = words[n] > 0 or any(s["count"][n].values())
                if has and not s["more"][n]:
                    self.error(s["id"], f"has level-{n} content but no data-more{n} description")
                if s["more"][n] and not has:
                    self.error(s["id"], f"data-more{n} is set but nothing is marked data-l=\"{n}\"")
                if s["more"][n] and re.search(r"[.!?]\s*$", s["more"][n]):
                    self.error(s["id"], f'data-more{n} is shown as "… adds <text>."; write it without a final full stop')
                if s["more"][n] and s["more"][n][:1].isupper() and not re.match(r"[A-Z]{2}", s["more"][n]):
                    self.warn(s["id"], f"data-more{n} continues a sentence (\"Mechanics adds …\"); start it in lower case")
            deeper = words[2] + words[3]
            if deeper and s["id"] not in SINGLE_LEVEL and (words[1] > 150 or words[1] > deeper):
                self.warn(s["id"], f"level 1 has {words[1]} words against {deeper} deeper; over 150, or over half the section, usually means detail that belongs lower")
            if s["count"][1]["figures"] + s["count"][1]["tables"] > 1 and s["id"] not in SINGLE_LEVEL:
                self.warn(s["id"], "more than one figure or table at depth 1")
        for section in self.sections:
            sid = section.attrs["id"]
            events = []  # ("h3", level, text) and ("block", level) in reading order

            def visit(node):
                for child in node.children:
                    if not isinstance(child, Node):
                        continue
                    if child.tag == "h3":
                        events.append(("h3", child.level, squash(child.text())))
                    elif child.tag == "div" and not child.classes:
                        visit(child)  # a plain wrapper, usually <div data-l="2">
                    elif "sh" not in child.classes:
                        events.append(("block", child.level, ""))
            visit(section)
            for i, (kind, level, text) in enumerate(events):
                if kind != "h3":
                    continue
                under = []
                for later in events[i + 1:]:
                    if later[0] == "h3" and later[1] <= level:
                        break
                    if later[0] == "block":
                        under.append(later[1])
                if not under:
                    self.error(sid, f'heading "{text}" has nothing under it')
                elif min(under) > level:
                    self.error(sid, f'heading "{text}" shows at depth {level} but everything under it needs depth {min(under)}')
            for node in section.walk():
                if node.tag == "code" and node.level == 1 and re.search(r"\w_\w|[=()]", node.text()) and not re.match(r"\s*(?:GET|POST|PUT|PATCH|DELETE|HEAD) /", node.text()):
                    self.level1_code.setdefault(sid, []).append(squash(node.text()))
        for sid, found in self.level1_code.items():
            self.warn(sid, f"column names or expressions at depth 1 ({', '.join(sorted(set(found))[:8])}): level 1 is plain words; move the detail to level 2 or 3")

    # -- requirements and terms --------------------------------------------------
    def requirements(self):
        section = self.by_id.get("requirements")
        if not section:
            return
        names = {}
        lists = {ul.attrs["data-reqs"]: ul for ul in section.all("ul") if ul.attrs.get("data-reqs")}
        for prefix in ("FR", "NFR"):
            if prefix not in lists:
                self.error("requirements", f'missing <ul data-reqs="{prefix}">')
        for prefix, ul in lists.items():
            if ul.level != 1:
                self.error("requirements", f"the {prefix} list must be visible at depth 1")
            for i, li in enumerate(c for c in ul.children if isinstance(c, Node) and c.tag == "li"):
                rid = f"{prefix}{i + 1}"
                first = [c for c in li.children if isinstance(c, Node) or c.strip()][:1]
                if not first or isinstance(first[0], str) or first[0].tag != "strong":
                    self.error("requirements", f"{rid} must open with its title in <strong>")
                    continue
                names[rid] = squash(first[0].text())
                text = squash(li.text())
                found = sorted(set(m.group(0) for m in re.finditer(r"\b(?:%s)\b" % MECHANISMS, text)))
                if found:
                    self.warn("requirements", f"{rid} names a mechanism ({', '.join(found)}): state the guarantee the reader can observe and leave the device to the design sections")
                if prefix == "NFR" and not re.search(r"\d", text):
                    self.warn("requirements", f"{rid} \"{names[rid]}\" has no number or bound; give one where it is meaningful")
                if not li.all(None) or not any(n.attrs.get("data-l") == "2" for n in li.walk()):
                    self.warn("requirements", f"{rid} has no level-2 explanation (<span data-l=\"2\">)")
        if not any(squash(h.text()).lower() == "out of scope" for h in section.all("h3")):
            self.warn("requirements", 'no "Out of scope" list: say which scope the design leaves out on purpose')
        delivered = {}
        for node in self.root.walk():
            if "data-req" in node.attrs:
                home = node.up(lambda n: n.tag == "section")
                where = home.attrs.get("id", "?") if home else "page"
                for rid in node.attrs["data-req"].split():
                    if rid not in names:
                        self.error(where, f'data-req="{rid}" is not a requirement of this page')
                    delivered.setdefault(rid, set()).add(where)
                if node.tag not in ("p", "li") and "brief" not in node.classes:
                    self.warn(where, "data-req belongs on the <p>, <li> or .brief that makes the claim")
        for rid in names:
            if not delivered.get(rid, set()) - {"requirements"}:
                self.error("requirements", f"{rid} \"{names[rid]}\" is not delivered anywhere: tag the sentence that implements it with data-req=\"{rid}\"")
        for section in self.sections:
            sid = section.attrs["id"]
            if section.attrs.get("data-num") and not any("data-req" in n.attrs for n in section.walk()):
                self.warn(sid, "a component section that serves no requirement: tag what it delivers, or ask why it is in the design")

    def terminology(self):
        ids = [s.attrs["id"] for s in self.sections]
        terms = self.by_id.get("terms")
        if terms:
            if "requirements" in ids and ids.index("terms") > ids.index("requirements"):
                self.error("terms", "core terms are defined before Requirements")
            rows = [tr for tr in terms.all("tr") if tr.attrs.get("id", "").startswith("term-")]
            if len(rows) < 2 or any(r.level != 1 for r in rows):
                self.error("terms", 'define each core term in a table row with id="term-…", visible at depth 1')
        glossary = [d for d in self.root.all("dl") if d.attrs.get("id") == "glossary"]
        if not glossary:
            self.warn("glossary", 'no <dl id="glossary">: terms of art get no hover definition')
            return
        if "hidden" not in glossary[0].attrs:
            self.error("glossary", "the glossary list must carry the hidden attribute")
        if glossary[0].up(lambda n: n.tag == "section"):
            self.error("glossary", "put the glossary after the last section, not inside one")
        prose = "\n".join(squash(n.text(("script", "style", "svg", "pre"))) for s in self.sections
                          for n in s.walk() if n.tag in ("p", "li", "td", "figcaption") or "brief" in n.classes)
        items = [c for c in glossary[0].children if isinstance(c, Node)]
        for i, dt in enumerate(items):
            if dt.tag != "dt":
                continue
            name = squash(dt.text())
            if i + 1 >= len(items) or items[i + 1].tag != "dd" or not squash(items[i + 1].text()):
                self.error("glossary", f'"{name}" has no <dd> definition right after it')
            pattern = dt.attrs.get("data-match") or r"\b" + re.escape(name) + r"s?\b"
            try:
                if not re.search(pattern, prose, 0 if "data-case" in dt.attrs else re.I):
                    self.warn("glossary", f'"{name}" never matches the text; remove it or fix data-match')
            except re.error as problem:
                self.error("glossary", f'"{name}": data-match is not a valid pattern ({problem})')

    # -- figures, code, numbers, data model, style ---------------------------------
    def figures(self):
        for section in self.sections:
            sid = section.attrs["id"]
            for figure in section.all("figure"):
                if not figure.all("figcaption"):
                    self.warn(sid, "a figure without a figcaption")
                if "steps" in figure.classes:
                    marks = [int(n.attrs["data-s"]) for n in figure.walk() if n.attrs.get("data-s", "").isdigit()]
                    notes = [li for ol in figure.all("ol", "stepnotes") for li in ol.children if isinstance(li, Node)]
                    if not marks or len(notes) != max(marks) or set(marks) != set(range(1, max(marks) + 1)):
                        self.error(sid, f"step-through figure: {len(set(marks))} steps marked data-s but {len(notes)} notes in <ol class=\"stepnotes\">; they must match, counting from 1")
            for svg in section.all("svg"):
                if svg.attrs.get("role") != "img" or not svg.attrs.get("aria-label"):
                    self.error(sid, 'a diagram needs role="img" and an aria-label that says what it shows')
                if not svg.attrs.get("viewbox"):  # the parser lower-cases attribute names
                    self.error(sid, "a diagram needs a viewBox so it scales")
                if re.search(r"#[0-9a-fA-F]{3,8}\b", " ".join(f"{k}={v}" for n in [svg, *svg.walk()] for k, v in n.attrs.items() if k in ("fill", "stroke", "style"))):
                    self.warn(sid, "hard-coded colour in a diagram: use var(--…) tokens so dark mode keeps working")
            for pre in section.all("pre"):
                if not [c for c in pre.children if isinstance(c, Node) and c.tag == "code"]:
                    self.error(sid, "code blocks are <pre><code>…</code></pre>")
                lang = pre.attrs.get("data-lang")
                if lang is None:
                    self.warn(sid, f'code block without data-lang ({", ".join(sorted(LANGS))}): "{squash(pre.text())[:40]}…"')
                elif lang not in LANGS:
                    self.error(sid, f'data-lang="{lang}" is not coloured yet: add it to LANGS in static/assets/guide.js and to LANGS in this script')
            for table in section.all("table"):
                if not table.up(lambda n: "scroll" in n.classes):
                    self.warn(sid, 'wrap tables in <div class="scroll"> so they scroll on a phone')
                if not table.all("th"):
                    self.warn(sid, "a table without a header row")

    def arithmetic(self):
        checked = 0
        for section in self.sections:
            for box in section.all(cls="formula"):
                for line in box.text().split("\n"):
                    for left, relation, right, a, b in relations(squash(line)):
                        checked += 1
                        slack = 0.1 if relation == "≈" else 0.005
                        if abs(a - b) > slack * max(abs(a), abs(b), 1e-9):
                            self.warn(section.attrs["id"], f'arithmetic: "{left} {relation} {right}" but the left side comes to {a:,.6g}')
        self.notes.append(f"recomputed {checked} formula steps")

    def data_model(self):
        columns = set()
        for box in self.root.all(cls="schema"):
            for li in box.all("li"):
                own = "".join(c for c in li.children if isinstance(c, str))
                columns |= set(re.findall(r"[a-z][a-z0-9_]*", own))
            columns |= {squash("".join(c for c in h.children if isinstance(c, str))) for h in box.all("h4")}
        if not columns:
            if any(s.all("pre") for s in self.sections):
                self.warn("data model", 'no <div class="schema"> found: a design with stored state shows its tables')
            return
        seen = {}
        for section in self.sections:
            for code in section.all("code"):
                text = code.text()
                sql = code.up(lambda n: n.tag == "pre") is None or re.match(r"\s*(SELECT|UPDATE|INSERT|DELETE|CREATE|ALTER|WITH)\b", text)
                if not sql:
                    continue
                text = re.sub(r"'[^']*'|\"[^\"]*\"|--[^\n]*", " ", text)
                for word in re.findall(r"(?<![\w.$-])[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?![\w(-])", text):
                    if word not in columns:
                        seen.setdefault(word, set()).add(section.attrs["id"])
        if seen:
            listing = "; ".join(f"{w} ({', '.join(sorted(s))})" for w, s in sorted(seen.items()))
            self.warn("data model", f"identifiers used in code but not listed in any schema table: {listing}. Each must be a column the schema shows, or clearly something else (a setting, a parameter, a shorthand the text defines)")

    def prose(self):
        todo = len(re.findall(r"\bTODO\b", self.source))
        if todo:
            self.error("page", f"{todo} TODO placeholders left from the skeleton")
        for section in self.sections:
            sid = section.attrs["id"]
            text = squash(section.text(("script", "style", "svg", "pre", "code")))
            if '"' in text or re.search(r"\w'\w|'\w|\w'", text):
                at = re.search(r".{0,25}[\"'].{0,25}", text).group(0)
                self.warn(sid, f"straight quotes in prose (…{at}…): the site uses “ ” and ’")
            if "—" in text:
                self.warn(sid, "an em dash in prose: the site uses commas, colons and parentheses")
            if re.search(r"\b(?:the )?(?:next|following|previous) section (?:explains|covers|describes|shows)|\bas (?:we|you) (?:saw|will see)\b|\bin this section\b", text, re.I):
                self.warn(sid, "a sentence that announces structure instead of saying something (rubrics/framing.md)")
        index = REPO / "pages/index.html"
        if index.is_file() and f'href="{self.path.name}"' not in index.read_text():
            self.warn("index", f"pages/index.html has no link to {self.path.name} yet")

    def build(self):
        if REPO / "pages" not in self.path.parents:
            self.notes.append("not built (the file is outside pages/)")
            return
        try:
            builder = load(REPO / "scripts/build.py", "build")
            builder.render(self.path)
        except Exception as problem:  # the build's own message says what to fix
            self.error("build", str(problem))

    def run(self):
        self.level1_code, self.notes = {}, []
        for step in (self.settings, self.styles, self.structure, self.depth, self.requirements,
                     self.terminology, self.figures, self.arithmetic, self.data_model, self.prose, self.build):
            step()
        return self


def number(token):
    match = re.fullmatch(r"(\d[\d,]*(?:\.\d+)?)(%?)", token)
    if not match:
        return None
    return float(match.group(1).replace(",", "")) / (100 if match.group(2) else 1)


def evaluate(text):
    """Value of 'a × b + c' with units read as words; None when it is not plain arithmetic."""
    tokens = text.replace("(", " ( ").replace(")", " ) ").split()
    out, last = [], None
    for i, token in enumerate(tokens):
        value = number(token)
        if value is not None:
            if last == "number":
                return None  # two numbers with no operator between them: a range or a list
            unit = tokens[i + 1].split("/")[0] if i + 1 < len(tokens) else ""
            out.append(repr(value * SIZES.get(unit, 1)))
            last = "number"
        elif token in ("×", "*", "÷", "/", "+", "−", "-"):
            out.append({"×": "*", "÷": "/", "−": "-"}.get(token, token))
            last = "operator"
        elif token in ("(", ")"):
            out.append(token)
        elif token in ("to", "and", "or") and last == "number":
            return None
    while out and out[-1] in "*/+-(":
        out.pop()
    while out and out[0] in "*/+)":
        out.pop(0)
    joined = " ".join(out)
    if not re.search(r"\d", joined) or re.search(r"[\d)] \(|\) \d|\( \)", joined):
        return None
    try:
        return float(eval(joined, {"__builtins__": {}}, {}))  # only numbers, operators and brackets reach here
    except Exception:
        return None


def relations(line):
    """Yield (left, relation, right, left value, right value) for each checkable step of a formula line."""
    if ": " in line:
        line = line.split(": ", 1)[1]
    found = []

    def inner(match):  # "(8% × 100,000 = 8,000)" is checked, then stands for its result
        parts = re.split(r"\s([=≈])\s", match.group(1))
        if len(parts) == 1:
            return match.group(0)
        found.extend(steps(parts))
        return parts[-1]

    def steps(parts):
        result = []
        for i in range(0, len(parts) - 2, 2):
            a, b = evaluate(parts[i]), evaluate(parts[i + 2])
            if a is not None and b is not None:
                result.append((parts[i].strip(), parts[i + 1], parts[i + 2].strip(), a, b))
        return result

    line = re.sub(r"\(([^()]*)\)", inner, line)
    return found + steps(re.split(r"\s([=≈])\s", line))


def numbers(check):
    """Each large number, and each number with a unit, with the sections that use it."""
    units = r"%|ms|s|KB|MB|GB|TB|days?|hours?|minutes?|seconds?|times|×"
    seen = {}
    for section in check.sections:
        text = squash(section.text(("script", "style", "svg", "pre")))
        for match in re.finditer(r"(?<![\w.,-])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?: ?(%s)(?![\w]))?" % units, text):
            value, unit = match.group(1), match.group(2)
            if unit or "," in value:
                seen.setdefault(f"{value} {unit or ''}".strip(), []).append(section.attrs["id"])
    for value, where in seen.items():
        counts = ", ".join(f"{s}×{where.count(s)}" for s in dict.fromkeys(where))
        print(f"{value:>14}  {counts}")


def main(argv):
    if not argv:
        sys.exit(__doc__)
    check = Check(argv[0])
    if "--numbers" in argv:
        return numbers(check)
    check.run()
    for line in check.errors:
        print("ERROR", line)
    for line in check.warnings:
        print("warn ", line)
    print(f"{len(check.errors)} errors, {len(check.warnings)} warnings; {'; '.join(check.notes)}")
    sys.exit(1 if check.errors else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
