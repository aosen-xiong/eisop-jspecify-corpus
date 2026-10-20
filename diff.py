#!/usr/bin/env python3
"""Compares two diagnostics.tsv files from the same project.

usage: diff.py <baseline diagnostics.tsv> <new diagnostics.tsv>

Diagnostics are matched on (tool, key, file, message), not line number, so unrelated edits that
shift lines do not show up as churn; capture variable numbers in a message are ignored too.  Prints added and removed diagnostics and exits 1 if any
EISOP diagnostic was added or removed.
"""

import collections
import csv
import re
import sys


def load(path):
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    # javac numbers capture variables in processing order, which changes between runs (capture#17 in
    # one run is capture#01 in the next), so the number is not part of a diagnostic's identity.
    ident = lambda r: (r["tool"], r["key"], r["file"], re.sub(r"capture#\d+", "capture#N", r["msg"]))
    return collections.Counter(map(ident, rows)), {ident(r): r for r in rows}


def main():
    base, base_rows = load(sys.argv[1])
    new, new_rows = load(sys.argv[2])
    added, removed = new - base, base - new
    for label, delta, rows in (("+", added, new_rows), ("-", removed, base_rows)):
        for ident, n in sorted(delta.items()):
            r = rows[ident]
            suffix = f" (x{n})" if n > 1 else ""
            print(f"{label} {r['tool']}\t{r['key']}\t{r['file']}:{r['line']}\t{r['msg']}{suffix}")
    eisop_changed = any(i[0] == "eisop" for i in list(added) + list(removed))
    print(f"added {sum(added.values())}, removed {sum(removed.values())}", file=sys.stderr)
    sys.exit(1 if eisop_changed else 0)


if __name__ == "__main__":
    main()
