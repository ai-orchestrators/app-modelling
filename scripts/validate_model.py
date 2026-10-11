#!/usr/bin/env python3
"""Validate a model document before anyone builds from it.

    python3 scripts/validate_model.py docs/model/website-model.md --kind website
    python3 scripts/validate_model.py docs/model/app-model.md --kind app

Exit 0 = the model is safe to build from. Exit 1 = fix the listed problems and
run again. Exit 2 = the command itself was wrong.

Python 3 standard library only. Reads one file, writes nothing.
"""
import argparse
import re
import sys

# The sections every model must carry, in the order the template gives them.
# A lens that was not run still keeps its heading, with "not run" and a reason.
REQUIRED = {
    "website": [
        "Summary",
        "Structure",
        "Design system",
        "Conversion path",
        "Content and voice",
        "Tech and delivery",
        "Customer evidence",
        "Evidence register",
        "Uncertain",
        "Build brief",
    ],
    "app": [
        "Summary",
        "Screens",
        "Flows",
        "Data model",
        "API and integrations",
        "Auth and roles",
        "Design system",
        "Shipped artifact",
        "User evidence",
        "Evidence register",
        "Uncertain",
        "Build brief",
    ],
}

HEADER_FIELDS = ["Source", "Modelled on", "Lenses run", "Right to analyse"]
CONFIDENCE = {"high", "medium", "low"}
EVIDENCE_ID = re.compile(r"E\d+$")
# Words that fill the evidence cell without pointing at anything.
NOT_EVIDENCE = {"unknown", "n/a", "na", "none", "-", "?", "see above", "assumed"}
# Placeholders that mean the author stopped before finishing.
UNFINISHED = re.compile(r"\b(TBD|TBC|TODO|FIXME)\b|\[\s*\.\.\.\s*\]|\{\{.*?\}\}|^_Write:")
# A section may be short, but one word is a heading with nothing under it.
MIN_SECTION_CHARS = 12


def split_sections(text):
    """Return {heading: body} for every level-2 heading, ignoring code fences."""
    sections, current, in_fence = {}, None, False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(body).strip() for name, body in sections.items()}


def check_header(text, problems):
    head = text.split("\n## ", 1)[0]
    for field in HEADER_FIELDS:
        match = re.search(r"\*\*%s:\*\*[ \t]*(.*)" % re.escape(field), head)
        if not match:
            problems.append(
                "Header field '**%s:**' is missing. The header needs: %s."
                % (field, ", ".join(HEADER_FIELDS))
            )
        elif not match.group(1).strip():
            problems.append("Header field '%s' is empty." % field)


def split_row(line):
    """Split one markdown table row into cells.

    A pipe inside `code` or written as \\| is part of the cell, not a divider.
    """
    cells, current, in_code, escaped = [], [], False, False
    for char in line.strip():
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "`":
            in_code = not in_code
            current.append(char)
        elif char == "|" and not in_code:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip())
    # A row written "| a | b |" has an empty cell before and after.
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return cells


def check_sections(sections, kind, problems):
    present = [name for name in sections if name in REQUIRED[kind]]
    expected = [name for name in REQUIRED[kind] if name in sections]
    if present != expected:
        problems.append(
            "Sections are out of order. Keep the template order: %s."
            % ", ".join(REQUIRED[kind]))
    for name in REQUIRED[kind]:
        if name not in sections:
            problems.append(
                "Section '## %s' is missing. Found: %s."
                % (name, ", ".join(sections) or "no level-2 headings")
            )
        elif len(sections[name]) < MIN_SECTION_CHARS:
            problems.append(
                "Section '## %s' is empty. Write the finding, or 'not run' or "
                "'not detected' with the reason." % name
            )


def check_size(summary, problems):
    """An app model has to commit to one size, so a quote can be built on it."""
    match = re.search(r"\*\*Size:\*\*[ \t]*(\S*)", summary)
    if not match or match.group(1).rstrip(".,;:").upper() not in ("S", "M", "L", "XL"):
        problems.append(
            "Summary needs a line '**Size:** S', M, L or XL, followed by what "
            "the size covers. Pick one size, not a range.")


def check_register(body, problems):
    """Every claim row needs an ID, a claim, evidence and a confidence."""
    rows = [split_row(line) for line in body.splitlines()
            if line.strip().startswith("|")]
    # Drop the header row and the |---|---| divider.
    rows = [r for r in rows if r and not set("".join(r)) <= set("-: ")][1:]
    if not rows:
        problems.append(
            "Evidence register has no claim rows. Each key claim needs a row: "
            "| ID | Claim | Evidence | Confidence |."
        )
        return
    seen = set()
    for row in rows:
        label = row[0] or "(no ID)"
        if len(row) != 4:
            problems.append(
                "Evidence row '%s' has %d cells, needs exactly 4 (ID, Claim, "
                "Evidence, Confidence). Write a pipe inside a cell as \\|."
                % (label, len(row))
            )
            continue
        if not EVIDENCE_ID.match(row[0]):
            problems.append(
                "Evidence ID '%s' is not valid. Use E01, E02 and so on." % label)
        elif row[0] in seen:
            problems.append("Evidence ID '%s' is used twice." % row[0])
        seen.add(row[0])
        if not row[1]:
            problems.append("Evidence row '%s' has no claim." % label)
        if not row[2] or row[2].lower() in NOT_EVIDENCE:
            problems.append(
                "Evidence row '%s' has no evidence. Name the URL, file and "
                "line, or screenshot it came from." % label
            )
        if row[3].lower() not in CONFIDENCE:
            problems.append(
                "Evidence row '%s' has confidence '%s'. Use high, medium or low."
                % (label, row[3])
            )


def check_unfinished(text, problems):
    in_fence = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and UNFINISHED.search(line):
            problems.append(
                "Line %d still has a placeholder: '%s'." % (number, line.strip()[:70])
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("model", help="path to the model markdown file")
    parser.add_argument("--kind", required=True, choices=sorted(REQUIRED))
    args = parser.parse_args()

    try:
        # utf-8-sig so a file saved with a byte-order mark still parses.
        with open(args.model, encoding="utf-8-sig") as handle:
            text = handle.read()
    except OSError as error:
        print("validate_model: cannot read %s (%s)." % (args.model, error.strerror))
        print("Write the model first, from templates/, then run this again.")
        return 2
    except UnicodeDecodeError:
        print("validate_model: %s is not UTF-8 text. Pass the model markdown "
              "file, saved as UTF-8." % args.model)
        return 2

    problems = []
    sections = split_sections(text)
    check_header(text, problems)
    check_sections(sections, args.kind, problems)
    if args.kind == "app" and "Summary" in sections:
        check_size(sections["Summary"], problems)
    if "Evidence register" in sections:
        check_register(sections["Evidence register"], problems)
    check_unfinished(text, problems)

    if problems:
        print("validate_model: %d problem(s) in %s" % (len(problems), args.model))
        for problem in problems:
            print("  - " + problem)
        print("Fix these in the model, then run the validator again.")
        return 1
    print("validate_model: OK. %s is complete enough to build from." % args.model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
