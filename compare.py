#!/usr/bin/env python3
"""Pairs EISOP and NullAway diagnostics from one diagnostics.tsv by source location.

usage: compare.py <diagnostics.tsv>

Both tools run in the same build, so their line numbers refer to the same source.  Diagnostics are joined on (file, line), not compared one to
one: EISOP reports several keys for one root cause -- override.typaram.invalid,
override.param.invalid and override.return.invalid on one overriding method -- where NullAway
reports one, so only locations are comparable.  An exact line match misses a pair when the two
tools anchor one problem on different lines of a multi-line construct.
"""

import collections
import csv
import sys

TOOLS = ("eisop", "nullaway")
GROUPS = (
    ("both", "Reported by both"),
    ("eisop-only", "Reported by EISOP only"),
    ("nullaway-only", "Reported by NullAway only"),
)


def cell(text):
    return text.replace("|", "\\|")


def short(path):
    marker = "/src/main/java/"
    return path.split(marker, 1)[1] if marker in path else path


def main():
    with open(sys.argv[1], encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
                if r["tool"] in TOOLS]

    locations = collections.defaultdict(lambda: {tool: [] for tool in TOOLS})
    for r in rows:
        locations[(r["file"], int(r["line"]))][r["tool"]].append(r)

    grouped = {name: [] for name, _ in GROUPS}
    for loc, by_tool in sorted(locations.items()):
        eisop, nullaway = by_tool["eisop"], by_tool["nullaway"]
        name = "both" if eisop and nullaway else "eisop-only" if eisop else "nullaway-only"
        grouped[name].append((loc, eisop, nullaway))

    counts = collections.Counter(r["tool"] for r in rows)
    print("# EISOP vs NullAway, by source location\n")
    print(f"- diagnostics: EISOP {counts['eisop']}, NullAway {counts['nullaway']}")
    print(f"- locations: {len(locations)} "
          + ", ".join(f"{name} {len(grouped[name])}" for name, _ in GROUPS))
    for name, title in GROUPS:
        if not grouped[name]:
            continue
        print(f"\n## {title} ({len(grouped[name])})\n")
        print("| location | EISOP keys | NullAway |")
        print("|---|---|---|")
        for (file, line), eisop, nullaway in grouped[name]:
            keys = collections.Counter(r["key"] for r in eisop)
            eisop_cell = ", ".join(f"`{k}`" + (f" x{n}" if n > 1 else "") for k, n in sorted(keys.items()))
            nullaway_cell = "; ".join(sorted({cell(r["msg"]) for r in nullaway}))
            print(f"| `{cell(short(file))}:{line}` | {eisop_cell} | {nullaway_cell} |")


if __name__ == "__main__":
    main()
