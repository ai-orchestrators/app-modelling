#!/usr/bin/env python3
"""Score a build against its model, from the feature matrix.

    python3 scripts/parity.py docs/model/features.csv
    python3 scripts/parity.py docs/model/features.csv --json

Columns: feature, area, priority, original, build, notes
  priority  must | should | could
  original  yes | no        (does the original have it? no = our own
                             addition, never scored)
  build     yes | partial | no | skip   (skip needs a reason in notes)

A must-have cannot be skipped. If it is truly out of scope, lower its priority
and say why in notes.

Exit 0 = every must-have is built and the score is 80 or more.
Exit 1 = a must-have is missing, partial or skipped, the score is under 80,
or a row is malformed. The printed lines say which.
Exit 2 = the command itself was wrong.

Python 3 standard library only. Reads one file, writes nothing.
"""
import argparse
import csv
import json
import sys

# A must-have counts three times a could-have. The gap is deliberate: one
# missing must-have should outweigh a full set of could-haves.
WEIGHT = {"must": 3, "should": 2, "could": 1}
# Partial work is half done until proven otherwise.
CREDIT = {"yes": 1.0, "partial": 0.5, "no": 0.0}
# Every must-have built is not enough on its own. Below 80 the rebuild is
# still missing a large share of what the original did day to day.
SHIP_SCORE = 80.0
COLUMNS = ["feature", "area", "priority", "original", "build", "notes"]


def load(path):
    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                return None, [
                    "Missing column(s): %s. The file needs: %s."
                    % (", ".join(missing), ", ".join(COLUMNS))
                ]
            return list(reader), []
    except OSError as error:
        return None, ["Cannot read %s (%s)." % (path, error.strerror)]
    except (UnicodeDecodeError, csv.Error) as error:
        return None, ["%s is not a readable UTF-8 CSV (%s). Start again from "
                      "templates/features.csv." % (path, error)]


def score(rows):
    errors, scored, missing = [], [], []
    for number, row in enumerate(rows, 2):  # row 1 is the header
        cell = {k: (row.get(k) or "").strip() for k in COLUMNS}
        name = cell["feature"] or "(row %d)" % number
        priority, build = cell["priority"].lower(), cell["build"].lower()
        original = cell["original"].lower()
        # Check the whole row before deciding whether it is scored, so a
        # malformed row can never drop out of the count unnoticed.
        row_errors = []
        if None in row:
            row_errors.append("has more than %d columns. Quote any cell that "
                              "contains a comma" % len(COLUMNS))
        if not cell["feature"]:
            row_errors.append("has no feature name")
        if priority not in WEIGHT:
            row_errors.append("has priority '%s'. Use must, should or could"
                              % cell["priority"])
        if original not in ("yes", "no"):
            row_errors.append("has original '%s'. Use yes or no: does the "
                              "original have this feature" % cell["original"])
        if build not in CREDIT and build != "skip":
            row_errors.append("has build '%s'. Use yes, partial, no or skip"
                              % cell["build"])
        if build == "skip" and not cell["notes"]:
            row_errors.append("is skip with no reason in notes")
        if build == "skip" and priority == "must" and original == "yes":
            row_errors.append("is a must-have marked skip. Build it, or lower "
                              "its priority and say why in notes")
        if row_errors:
            errors.extend("Row %d '%s' %s." % (number, name, e) for e in row_errors)
            continue
        if original == "no" or build == "skip":
            continue  # our own addition, or left out on purpose
        scored.append((cell, WEIGHT[priority], CREDIT[build]))
        if build != "yes":
            missing.append(cell)
    return scored, missing, errors


def summarise(scored, missing):
    total = sum(weight for _, weight, _ in scored)
    earned = sum(weight * credit for _, weight, credit in scored)
    musts = [c for c, _, _ in scored if c["priority"].lower() == "must"]
    musts_done = [c for c in musts if c["build"].lower() == "yes"]
    areas = {}
    for cell, weight, credit in scored:
        area = areas.setdefault(cell["area"] or "unsorted", [0.0, 0])
        area[0] += weight * credit
        area[1] += weight
    order = {"must": 0, "should": 1, "could": 2}
    missing.sort(key=lambda c: (order[c["priority"].lower()], c["area"], c["feature"]))
    points = round(100 * earned / total, 1) if total else 0.0
    return {
        "score": points,
        "musts_done": len(musts_done),
        "musts_total": len(musts),
        "shippable": (len(musts_done) == len(musts) and bool(scored)
                      and points >= SHIP_SCORE),
        "areas": {
            name: round(100 * got / of, 1)
            for name, (got, of) in sorted(areas.items(), key=lambda kv: kv[1][0] / kv[1][1])
        },
        "missing": [
            {k: c[k] for k in ("feature", "area", "priority", "build", "notes")}
            for c in missing
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("features", help="path to features.csv")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args()

    rows, errors = load(args.features)
    if rows is None:
        print("parity: " + errors[0])
        return 2
    scored, missing, errors = score(rows)
    result = summarise(scored, missing)
    result["errors"] = errors

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("Parity score: %s/100" % result["score"])
        print("Must-haves:   %d of %d built" % (result["musts_done"], result["musts_total"]))
        for name, value in result["areas"].items():
            print("  %-24s %5.1f" % (name[:24], value))
        if result["missing"]:
            print("Still to build, in order:")
            for item in result["missing"]:
                print("  [%s] %s (%s) %s" % (
                    item["priority"], item["feature"], item["build"], item["notes"]))
        for error in errors:
            print("ERROR: " + error)
        print("Verdict: " + ("shippable" if result["shippable"] and not errors
                             else "not shippable"))
    return 0 if result["shippable"] and not errors else 1


if __name__ == "__main__":
    sys.exit(main())
