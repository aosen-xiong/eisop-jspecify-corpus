#!/usr/bin/env python3
"""Compares two diagnostics.tsv files from the same project and arm.

usage: diff.py <baseline diagnostics.tsv> <new diagnostics.tsv>

Diagnostics are matched on (tool, key, file, message), not line number, so unrelated edits that
shift lines do not show up as churn.  Prints added and removed diagnostics and exits 1 if any
EISOP diagnostic was added or removed.
"""

import collections
import csv
import sys


def load(path):
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    ident = lambda r: (r["tool"], r["key"], r["file"], r["msg"])
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
