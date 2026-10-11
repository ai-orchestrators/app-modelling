#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static parse of a site or a codebase for its declared design layer.

No browser, no agent loop, no tokens burned. Fetches (or reads) CSS, parses it
for the declared design layer, frequency-ranks what it finds, and prints JSON.

The agent reads that JSON and writes the design section of the model. This
script never writes that document and never writes to CLAUDE.md, AGENTS.md or
SKILL.md.

Two hard rules, both deliberate:
  1. Never execute a scanned file. Config files are parsed as text, never
     imported, never eval'd. A scanned repo is untrusted input.
  2. Never send the target to a third-party service. Only the page and the
     stylesheets it links are fetched. Those stylesheets can sit on a CDN.

Usage:
    static_parse.py --url <site-url>
    static_parse.py --dir ./my-app
    static_parse.py --url <site-url> --out /tmp/raw.json

Exit 0 with usable JSON, or exit 1 with an error on stderr. Empty findings are
a result, not a failure: they mean the source has no declared token layer, and
the caller should fall back to computed styles read in a browser.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

TIMEOUT = 8
MAX_CSS_FILES = 40
MAX_WORKERS = 8
MAX_BYTES = 4 * 1024 * 1024
UA = "Mozilla/5.0 (compatible; design-static-parse/1.0)"

SOURCE_EXTS = {".css", ".scss", ".sass", ".less"}
CODE_EXTS = {".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte"}
SKIP_DIRS = {
    "node_modules", ".git", ".next", "dist", "build", ".venv", "__pycache__",
    ".turbo", ".cache", "coverage", ".svelte-kit", "out", "vendor",
}

# --- patterns -------------------------------------------------------------

RE_CUSTOM_PROP = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+)")
RE_HEX = re.compile(r"#(?:[0-9a-fA-F]{3,4}){1,2}\b")
RE_FUNC_COLOR = re.compile(
    r"\b(?:rgba?|hsla?|oklch|oklab|lab|lch|color)\([^()]*\)", re.IGNORECASE
)
RE_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;{}]+)", re.IGNORECASE)
RE_FONT_SIZE = re.compile(r"font-size\s*:\s*([0-9.]+)(px|rem|em)", re.IGNORECASE)
RE_FONT_WEIGHT = re.compile(r"font-weight\s*:\s*(\d{3}|bold|normal)", re.IGNORECASE)
RE_LINE_HEIGHT = re.compile(r"line-height\s*:\s*([0-9.]+)(px|rem|em)?", re.IGNORECASE)
RE_LETTER_SPACING = re.compile(r"letter-spacing\s*:\s*(-?[0-9.]+)(px|rem|em)", re.IGNORECASE)
RE_RADIUS = re.compile(r"border-radius\s*:\s*([^;{}]+)", re.IGNORECASE)
RE_SHADOW = re.compile(r"box-shadow\s*:\s*([^;{}]+)", re.IGNORECASE)
RE_SPACING = re.compile(
    r"(?:margin|padding|gap|row-gap|column-gap)(?:-(?:top|right|bottom|left|inline|block))?"
    r"\s*:\s*([^;{}]+)",
    re.IGNORECASE,
)
RE_LEN = re.compile(r"(-?[0-9.]+)(px|rem)")
RE_ZINDEX = re.compile(r"z-index\s*:\s*(-?\d+)", re.IGNORECASE)
RE_MAXWIDTH = re.compile(r"max-width\s*:\s*([0-9.]+)(px|rem)", re.IGNORECASE)
RE_DURATION = re.compile(
    r"(?:transition|animation)(?:-duration)?\s*:[^;{}]*?([0-9.]+)(ms|s)", re.IGNORECASE
)
RE_EASING = re.compile(
    r"(cubic-bezier\([^()]*\)|ease-in-out|ease-in|ease-out|linear|steps\([^()]*\))",
    re.IGNORECASE,
)
RE_KEYFRAMES = re.compile(r"@keyframes\s+([A-Za-z0-9_-]+)", re.IGNORECASE)
RE_MEDIA_WIDTH = re.compile(
    r"@media[^{]*?\(\s*(?:min|max)-width\s*:\s*([0-9.]+)(px|rem|em)", re.IGNORECASE
)
RE_DARK = re.compile(
    r"(prefers-color-scheme\s*:\s*dark|\.dark\b|\[data-theme=[\"']?dark|:root\.dark)",
    re.IGNORECASE,
)
RE_LINK_CSS = re.compile(
    r"<link\b[^>]*?rel\s*=\s*[\"']?stylesheet[\"']?[^>]*?>", re.IGNORECASE
)
RE_HREF = re.compile(r"href\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
RE_STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
RE_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


RE_VAR = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)\s*(?:,([^()]*))?\)")


def _resolve(value, tokens, depth=0):
    """Expand var(--x) against the declared token map.

    Sites that declare a token layer reference it everywhere, so an unresolved
    'var(--font-regular)' tells the agent nothing. Depth-capped: token maps
    self-reference and a cycle would otherwise hang.
    """
    if depth > 4 or "var(" not in value:
        return value

    def sub(m):
        name, fallback = m.group(1), (m.group(2) or "").strip()
        target = tokens.get(name)
        if target is not None:
            return _resolve(target, tokens, depth + 1)
        return fallback or m.group(0)

    return " ".join(RE_VAR.sub(sub, value).split())


def _rank(counter, limit, tokens=None):
    """Frequency-ranked list. The count is the signal: one use is noise."""
    out = []
    for v, n in counter.most_common(limit):
        row = OrderedDict([("value", v), ("count", n)])
        if tokens:
            resolved = _resolve(v, tokens)
            if resolved != v:
                row["resolves_to"] = resolved
        out.append(row)
    return out


def _fetch(url):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=TIMEOUT) as res:
        raw = res.read(MAX_BYTES)
    charset = "utf-8"
    try:
        charset = res.headers.get_content_charset() or "utf-8"
    except Exception:
        pass
    return raw.decode(charset, errors="replace")


# --- collection -----------------------------------------------------------


def collect_css_from_url(url):
    """Return (list of css strings, notes). Only ever contacts the target host."""
    notes = []
    try:
        html = _fetch(url)
    except Exception as exc:
        raise SystemExit("could not fetch %s: %s" % (url, exc))

    sheets = []
    for block in RE_STYLE_BLOCK.findall(html):
        if block.strip():
            sheets.append(block)

    fonts = []
    hrefs = []
    for tag in RE_LINK_CSS.findall(html):
        m = RE_HREF.search(tag)
        if not m:
            continue
        href = urljoin(url, m.group(1))
        if "fonts.googleapis.com" in href:
            fonts.append(href)
            continue
        hrefs.append(href)

    targets = hrefs[:MAX_CSS_FILES]

    def grab(href):
        try:
            return href, _fetch(href), None
        except Exception as exc:
            return href, None, str(exc)

    if targets:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            for href, body, err in pool.map(grab, targets):
                if body is not None:
                    sheets.append(body)
                else:
                    notes.append("stylesheet unreachable: %s (%s)" % (href, err))

    if len(hrefs) > MAX_CSS_FILES:
        notes.append(
            "%d stylesheets found, parsed the first %d"
            % (len(hrefs), MAX_CSS_FILES)
        )
    if not sheets:
        notes.append(
            "no stylesheets parsed - site is likely JS-rendered, fall back to computed styles in a browser"
        )
    return sheets, fonts, notes


def collect_css_from_dir(root):
    """Read stylesheets and inline styles from a codebase. Never executes a file."""
    notes = []
    sheets = []
    base = Path(root)
    if not base.is_dir():
        raise SystemExit("not a directory: %s" % root)

    count = 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            ext = Path(fn).suffix.lower()
            if ext not in SOURCE_EXTS and ext not in CODE_EXTS:
                continue
            p = Path(dirpath) / fn
            try:
                if p.stat().st_size > MAX_BYTES:
                    continue
                sheets.append(p.read_text(encoding="utf-8", errors="replace"))
                count += 1
            except Exception:
                continue
    if not count:
        notes.append("no stylesheet or component source found under %s" % root)
    return sheets, count, notes


def find_config_files(root):
    """Locate token configs. Reported as paths + raw text only, never imported."""
    base = Path(root)
    wanted = re.compile(
        r"^(tailwind\.config\.(js|cjs|mjs|ts)|theme\.(js|ts|json)|"
        r"tokens?\.json|design-tokens?\.(json|js|ts)|globals?\.css)$",
        re.IGNORECASE,
    )
    found = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if wanted.match(fn):
                found.append(str((Path(dirpath) / fn).relative_to(base)))
    return sorted(found)


def detect_ui_library(root):
    """Read package.json as data. Parsed with json, never executed."""
    pkg = Path(root) / "package.json"
    if not pkg.is_file():
        return None, []
    try:
        data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None, []
    deps = {}
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        got = data.get(key)
        if isinstance(got, dict):
            deps.update(got)
    names = set(deps)
    known = OrderedDict([
        ("shadcn", ("class-variance-authority", "@radix-ui/react-slot")),
        ("MUI", ("@mui/material",)),
        ("Chakra", ("@chakra-ui/react",)),
        ("Mantine", ("@mantine/core",)),
        ("Ant Design", ("antd",)),
        ("Bootstrap", ("bootstrap",)),
        ("Tailwind", ("tailwindcss",)),
    ])
    hits = [lib for lib, pkgs in known.items() if names.intersection(pkgs)]
    icons = [n for n in sorted(names) if "icon" in n.lower() or n in ("lucide-react", "react-feather")]
    return (hits or None), icons


# --- parsing --------------------------------------------------------------


def parse(sheets):
    tokens = OrderedDict()
    colors = Counter()
    families = Counter()
    sizes = Counter()
    weights = Counter()
    line_heights = Counter()
    tracking = Counter()
    radii = Counter()
    shadows = Counter()
    spacing = Counter()
    z_index = Counter()
    max_widths = Counter()
    durations = Counter()
    easings = Counter()
    keyframes = Counter()
    breakpoints = Counter()
    dark_signals = 0

    for raw in sheets:
        css = RE_COMMENT.sub(" ", raw)

        for name, value in RE_CUSTOM_PROP.findall(css):
            value = " ".join(value.split())
            if value and name not in tokens:
                tokens[name] = value

        for m in RE_HEX.findall(css):
            colors[m.lower()] += 1
        for m in RE_FUNC_COLOR.findall(css):
            norm = " ".join(m.split()).lower()
            if "rgba(0, 0, 0, 0)" in norm or norm.startswith("color("):
                continue
            colors[norm] += 1

        for fam in RE_FONT_FAMILY.findall(css):
            fam = " ".join(fam.split()).strip().rstrip(";")
            if fam:
                families[fam] += 1
        for val, unit in RE_FONT_SIZE.findall(css):
            sizes["%s%s" % (val, unit)] += 1
        for w in RE_FONT_WEIGHT.findall(css):
            weights[w.lower()] += 1
        for val, unit in RE_LINE_HEIGHT.findall(css):
            line_heights["%s%s" % (val, unit or "")] += 1
        for val, unit in RE_LETTER_SPACING.findall(css):
            tracking["%s%s" % (val, unit)] += 1

        for r in RE_RADIUS.findall(css):
            r = " ".join(r.split()).strip().rstrip(";")
            if r and r != "0":
                radii[r] += 1
        for s in RE_SHADOW.findall(css):
            s = " ".join(s.split()).strip().rstrip(";")
            if s and s.lower() != "none":
                shadows[s] += 1

        for decl in RE_SPACING.findall(css):
            for val, unit in RE_LEN.findall(decl):
                if val in ("0", "0.0"):
                    continue
                spacing["%s%s" % (val, unit)] += 1

        for z in RE_ZINDEX.findall(css):
            z_index[z] += 1
        for val, unit in RE_MAXWIDTH.findall(css):
            max_widths["%s%s" % (val, unit)] += 1

        for val, unit in RE_DURATION.findall(css):
            ms = float(val) * (1000.0 if unit.lower() == "s" else 1.0)
            if ms > 0:
                durations["%dms" % int(round(ms))] += 1
        for e in RE_EASING.findall(css):
            easings[" ".join(e.split()).lower()] += 1
        for k in RE_KEYFRAMES.findall(css):
            keyframes[k] += 1

        for val, unit in RE_MEDIA_WIDTH.findall(css):
            breakpoints["%s%s" % (val, unit)] += 1

        dark_signals += len(RE_DARK.findall(css))

    color_tokens = OrderedDict(
        (k, _resolve(v, tokens)) for k, v in tokens.items()
        if RE_HEX.search(v) or RE_FUNC_COLOR.search(v)
        or RE_HEX.search(_resolve(v, tokens)) or RE_FUNC_COLOR.search(_resolve(v, tokens))
    )

    return OrderedDict([
        ("declared_tokens", OrderedDict([
            ("count", len(tokens)),
            ("colour_tokens", color_tokens),
            ("all", tokens),
        ])),
        ("colours", _rank(colors, 40)),
        ("typography", OrderedDict([
            ("families", _rank(families, 12, tokens)),
            ("sizes", _rank(sizes, 20)),
            ("weights", _rank(weights, 10)),
            ("line_heights", _rank(line_heights, 12)),
            ("letter_spacing", _rank(tracking, 10)),
        ])),
        ("spacing", _rank(spacing, 24)),
        ("shape", OrderedDict([("radius", _rank(radii, 15, tokens))])),
        ("depth", OrderedDict([("shadows", _rank(shadows, 12, tokens))])),
        ("layout", OrderedDict([
            ("container_max_widths", _rank(max_widths, 10)),
            ("z_index", _rank(z_index, 12)),
        ])),
        ("motion", OrderedDict([
            ("durations", _rank(durations, 12)),
            ("easings", _rank(easings, 10)),
            ("keyframes", _rank(keyframes, 15)),
        ])),
        ("responsive", OrderedDict([("breakpoints", _rank(breakpoints, 12))])),
        ("dark_mode", OrderedDict([
            ("signals", dark_signals),
            ("detected", dark_signals > 0),
        ])),
    ])


def coverage(result):
    """Which of the twelve design sections the static parse actually filled."""
    got = []
    missing = []

    def check(label, ok):
        (got if ok else missing).append(label)

    check("colour", bool(result["colours"]))
    check("typography", bool(result["typography"]["families"]) or bool(result["typography"]["sizes"]))
    check("spacing", bool(result["spacing"]))
    check("shape", bool(result["shape"]["radius"]))
    check("depth", bool(result["depth"]["shadows"]))
    check("layout", bool(result["layout"]["container_max_widths"]) or bool(result["layout"]["z_index"]))
    check("motion", bool(result["motion"]["durations"]) or bool(result["motion"]["keyframes"]))
    check("responsive", bool(result["responsive"]["breakpoints"]))
    check("dark mode", result["dark_mode"]["detected"])

    # Never inferable from static CSS alone.
    always_missing = ["theme and atmosphere", "components", "do and do not"]
    return OrderedDict([
        ("filled", got),
        ("needs_path_a_or_judgement", missing + always_missing),
    ])


def main():
    ap = argparse.ArgumentParser(
        description="Static CSS parse of a site or codebase. No browser."
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="live site to parse")
    src.add_argument("--dir", help="local codebase to parse")
    ap.add_argument("--out", help="write JSON here instead of stdout")
    args = ap.parse_args()

    meta = OrderedDict()
    fonts = []

    if args.url:
        parsed = urlparse(args.url)
        if parsed.scheme not in ("http", "https"):
            raise SystemExit("--url must be http or https")
        sheets, fonts, notes = collect_css_from_url(args.url)
        meta["source"] = args.url
        meta["mode"] = "url"
        meta["stylesheets_parsed"] = len(sheets)
    else:
        sheets, count, notes = collect_css_from_dir(args.dir)
        meta["source"] = str(Path(args.dir).resolve())
        meta["mode"] = "dir"
        meta["files_parsed"] = count
        meta["config_files"] = find_config_files(args.dir)
        lib, icons = detect_ui_library(args.dir)
        meta["ui_library"] = lib
        meta["icon_packages"] = icons

    result = parse(sheets)
    meta["google_fonts_links"] = fonts
    meta["notes"] = notes

    payload = OrderedDict([
        ("meta", meta),
        ("coverage", coverage(result)),
        ("extracted", result),
    ])

    text = json.dumps(payload, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print("wrote %s" % args.out, file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
