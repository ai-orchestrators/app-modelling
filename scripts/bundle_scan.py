#!/usr/bin/env python3
"""Scan a BUILT output folder for things that should not ship.

    python3 scripts/bundle_scan.py dist
    python3 scripts/bundle_scan.py .next --json

Reports source maps, secret-shaped strings, public env names and every host
the bundle talks to. Use it on our own build output (dist, build, .next, out),
never on source and never on someone else's code.

Exit 0 = every text file was read and nothing needs fixing.
Exit 1 = source maps or secret-shaped strings found, or the scan was
incomplete (a file was skipped, or nothing was scanned).
Exit 2 = the command itself was wrong.

Python 3 standard library only. Reads files as text, never runs or imports
them, follows no symlinks, contacts nothing, writes nothing.
"""
import argparse
import base64
import binascii
import json
import os
import re
import sys

# Built JS chunks are rarely above a few MB. Files past this are media or
# data blobs, and reading them whole is how a scan runs out of memory.
MAX_FILE_BYTES = 8 * 1024 * 1024
# A real build has thousands of files, not hundreds of thousands. Past this
# the folder is almost certainly node_modules or the wrong path.
MAX_FILES = 20000
TEXT_SUFFIXES = (".js", ".mjs", ".cjs", ".html", ".css", ".json", ".txt", ".xml", ".map")
SKIP_DIRS = {"node_modules", ".git", "cache"}
# Show enough of a hit to find it, never enough to use it.
MASK_KEEP = 6

SECRET_PATTERNS = [
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Stripe live secret", re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{16,}\b")),
    ("OpenAI or Anthropic key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{24,}\b")),
    ("Resend key", re.compile(r"\bre_[A-Za-z0-9_]{12,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    # "apiKey" is left out on purpose: public API keys (maps, Firebase) use
    # that name in every bundle. Known key formats are caught above by shape.
    ("named secret", re.compile(
        r"(?i)\b(?:api[_-]?secret|client[_-]?secret|secret[_-]?key|private[_-]?key)"
        r"\b[\"']?\s*[:=]\s*[\"'][A-Za-z0-9_\-/+=]{16,}[\"']")),
]
# A JWT is three base64url parts. Most in a bundle are public (anon keys).
# The payload is decoded so only a service-role token is flagged.
JWT = re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.(eyJ[A-Za-z0-9_\-]{8,})\.[A-Za-z0-9_\-]{8,}")
ENV_NAME = re.compile(r"\b(?:NEXT_PUBLIC|VITE|PUBLIC|REACT_APP|NUXT_PUBLIC|GATSBY)_[A-Z0-9_]{2,}\b")
HOST = re.compile(r"https?://([A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
MAP_COMMENT = re.compile(r"sourceMappingURL=(\S+)")
# Hosts that appear in every bundle and tell us nothing.
BORING_HOSTS = {"www.w3.org", "reactjs.org", "react.dev", "fb.me", "nextjs.org",
                "developer.mozilla.org", "github.com", "schema.org", "example.com"}


def is_service_role(payload_b64):
    """True when a JWT payload claims the service_role role."""
    try:
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, binascii.Error):
        return False
    return isinstance(claims, dict) and claims.get("role") == "service_role"


def mask(value):
    return value[:MASK_KEEP] + "..." + " (%d chars)" % len(value)


def describe_map_target(target):
    """Say where a sourceMappingURL points without echoing it.

    The target can carry a token in its query string, and an inline data: map
    holds the source itself, so neither is ever printed in full.
    """
    if target.startswith("data:"):
        return "inline map (source embedded in this file)"
    host = HOST.match(target)
    if host:
        return "remote map on " + host.group(1).lower()
    return "map file " + os.path.basename(target.split("?", 1)[0].split("#", 1)[0])[:60]


def walk(root):
    """Yield text files under root. No symlinks, no dependency folders."""
    count = 0
    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS
                   and not os.path.islink(os.path.join(folder, d))]
        for name in sorted(files):
            path = os.path.join(folder, name)
            if os.path.islink(path) or not name.lower().endswith(TEXT_SUFFIXES):
                continue
            count += 1
            if count > MAX_FILES:
                raise RuntimeError(
                    "More than %d files. Point this at the build output folder "
                    "(dist, build, .next, out), not the project root." % MAX_FILES)
            yield path


def scan(root):
    report = {"root": root, "files_scanned": 0, "skipped": [],
              "source_maps": [], "map_comments": [], "secrets": [],
              "public_env_names": {}, "hosts": {}}
    for path in walk(root):
        rel = os.path.relpath(path, root)
        if rel.lower().endswith(".map"):
            report["source_maps"].append(rel)
            continue
        try:
            size = os.path.getsize(path)
            if size > MAX_FILE_BYTES:
                report["skipped"].append("%s (%.1f MB, over the %d MB limit)" % (
                    rel, size / 1048576.0, MAX_FILE_BYTES // 1048576))
                continue
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError as error:
            report["skipped"].append("%s (unreadable: %s)" % (rel, error.strerror))
            continue
        report["files_scanned"] += 1
        for match in MAP_COMMENT.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            report["map_comments"].append(
                {"file": rel, "line": line, "points_to": describe_map_target(match.group(1))})
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                report["secrets"].append(
                    {"file": rel, "line": line, "kind": label, "value": mask(match.group(0))})
        for match in JWT.finditer(text):
            if is_service_role(match.group(1)):
                line = text.count("\n", 0, match.start()) + 1
                report["secrets"].append(
                    {"file": rel, "line": line, "kind": "service-role JWT",
                     "value": mask(match.group(0))})
        for name in ENV_NAME.findall(text):
            report["public_env_names"][name] = report["public_env_names"].get(name, 0) + 1
        for host in HOST.findall(text):
            host = host.lower()
            if host not in BORING_HOSTS:
                report["hosts"][host] = report["hosts"].get(host, 0) + 1
    report["hosts"] = dict(sorted(report["hosts"].items(), key=lambda kv: -kv[1]))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("build_dir", help="built output folder: dist, build, .next, out")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args()

    if os.path.islink(args.build_dir):
        print("bundle_scan: '%s' is a symlink. Pass the real build folder so the "
              "scan cannot be pointed somewhere else." % args.build_dir)
        return 2
    if not os.path.isdir(args.build_dir):
        print("bundle_scan: '%s' is not a folder. Build the project first, then "
              "pass its output folder (dist, build, .next, out)." % args.build_dir)
        return 2
    try:
        report = scan(args.build_dir)
    except RuntimeError as error:
        print("bundle_scan: %s" % error)
        return 2

    findings = bool(report["source_maps"] or report["map_comments"] or report["secrets"])
    # A scan that skipped a file, or read nothing, has not cleared the build.
    incomplete = bool(report["skipped"]) or report["files_scanned"] == 0
    report["verdict"] = ("FIX BEFORE SHIP" if findings
                         else "INCOMPLETE" if incomplete else "clean")
    if args.json:
        print(json.dumps(report, indent=2))
        return 1 if findings or incomplete else 0

    print("bundle_scan: %d text files in %s" % (report["files_scanned"], args.build_dir))
    if report["files_scanned"] == 0:
        print("  Nothing scanned. Is this the build output folder?")
    print("Source map files: %d" % len(report["source_maps"]))
    for item in report["source_maps"][:20]:
        print("  " + item)
    print("sourceMappingURL comments: %d" % len(report["map_comments"]))
    for item in report["map_comments"][:20]:
        print("  %s:%d -> %s" % (item["file"], item["line"], item["points_to"]))
    print("Secret-shaped strings: %d" % len(report["secrets"]))
    for item in report["secrets"][:40]:
        print("  %s:%d  %s  %s" % (item["file"], item["line"], item["kind"], item["value"]))
    print("Public env names baked in: %d" % len(report["public_env_names"]))
    for name in sorted(report["public_env_names"]):
        print("  " + name)
    print("Hosts the bundle names: %d" % len(report["hosts"]))
    for host, count in list(report["hosts"].items())[:30]:
        print("  %-40s %d" % (host, count))
    if report["skipped"]:
        print("NOT SCANNED, check these by hand: %d" % len(report["skipped"]))
        for item in report["skipped"]:
            print("  " + item)
    print("Verdict: " + report["verdict"])
    print("Every hit is a lead, not a verdict. Open the file and check it.")
    return 1 if findings or incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
