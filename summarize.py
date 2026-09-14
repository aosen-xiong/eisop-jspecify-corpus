#!/usr/bin/env python3
"""Turns one arm's build.log into diagnostics.tsv, counts.tsv and summary.md.

usage: summarize.py <project-source-dir> <result-dir>

Each diagnostic is attributed to a tool (eisop, nullaway, errorprone, javac) and checked against
the project's @NullMarked scope: under -AonlyAnnotatedFor an EISOP diagnostic outside that scope
should not exist, so any such diagnostic is listed as a scoping anomaly.
"""

import collections
import os
import re
import sys

DIAG = re.compile(
    r"^(?P<file>/\S+\.java):(?P<line>\d+): (?P<kind>warning|error): "
    r"\[(?P<key>[^\]]+)\] (?P<msg>.*)$"
)
# javac -Xlint categories, which share the "[key]" format with Checker Framework keys.
JAVAC_LINT = {
    "auxiliaryclass", "cast", "classfile", "dangling-doc-comments", "deprecation", "dep-ann",
    "divzero", "empty", "exports", "fallthrough", "finally", "identity", "incubating",
    "lossy-conversions", "missing-explicit-ctor", "module", "opens", "options",
    "output-file-clash", "overloads", "overrides", "path", "preview", "processing", "rawtypes",
    "removal", "requires-automatic", "requires-transitive-automatic", "restricted", "serial",
    "static", "strictfp", "synchronization", "text-blocks", "this-escape", "try", "unchecked",
    "varargs",
}
CRASH = re.compile(r"The Checker Framework crashed|\.crashed\]|An exception has occurred in the compiler")
MARKED = re.compile(r"@(?:org\.jspecify\.annotations\.)?NullMarked\b")
UNMARKED = re.compile(r"@(?:org\.jspecify\.annotations\.)?NullUnmarked\b")
NULLAWAY_SUPPRESSION = re.compile(r"@SuppressWarnings\([^)]*\"NullAway[^\"]*\"")


def tool_of(key):
    if key.startswith("NullAway"):
        return "nullaway"
    if key in JAVAC_LINT:
        return "javac"
    if key[:1].isupper():
        return "errorprone"
    return "eisop"


def scan_sources(src):
    """Returns (marked package dirs, files mentioning @NullMarked, NullAway suppression sites)."""
    marked_dirs, marked_files, suppressions = set(), set(), []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in (".git", "build", ".gradle", "node_modules")]
        for fn in filenames:
            if not fn.endswith(".java"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except OSError:
                continue
            text = "".join(lines)
            if fn == "package-info.java":
                if MARKED.search(text):
                    marked_dirs.add(dirpath)
            elif MARKED.search(text) or UNMARKED.search(text):
                marked_files.add(path)
            for i, line in enumerate(lines, 1):
                if NULLAWAY_SUPPRESSION.search(line):
                    suppressions.append((path, i))
    return marked_dirs, marked_files, suppressions


def main():
    src, out = os.path.realpath(sys.argv[1]), sys.argv[2]
    marked_dirs, marked_files, suppressions = scan_sources(src)
    suppressed_files = {p for p, _ in suppressions}

    diags, crashes, unanchored, seen = [], [], [], set()
    canary_hits = collections.defaultdict(set)
    with open(os.path.join(out, "build.log"), encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if CRASH.search(line):
                crashes.append(line)
            if line.startswith("error: "):
                # Not tied to a source file, e.g. the checker failing to initialize.
                unanchored.append(line)
            m = DIAG.match(line)
            if not m:
                continue
            if m.group("file").endswith("/EisopCorpusCanary.java"):
                where = "unmarked" if "/eisopcorpus/unmarked/" in m.group("file") else "marked"
                canary_hits[where].add(tool_of(m.group("key")))
                continue
            d = m.groupdict()
            path = os.path.realpath(d["file"])
            # Gradle can replay a task's output; count each diagnostic once.
            ident = (path, d["line"], d["key"], d["msg"])
            if ident in seen:
                continue
            seen.add(ident)
            d["tool"] = tool_of(d["key"])
            d["file"] = os.path.relpath(path, src)
            # A class-level @NullMarked/@NullUnmarked file is reported as "class", since this
            # textual scan cannot tell which of its members are in scope.
            if os.path.dirname(path) in marked_dirs:
                d["scope"] = "package"
            elif path in marked_files:
                d["scope"] = "class"
            else:
                d["scope"] = "unmarked"
            d["nullaway_suppressed_file"] = "yes" if path in suppressed_files else "no"
            diags.append(d)

    cols = ["tool", "kind", "key", "scope", "nullaway_suppressed_file", "file", "line", "msg"]
    with open(os.path.join(out, "diagnostics.tsv"), "w", encoding="utf-8") as f:
        f.write("\t".join(cols) + "\n")
        for d in sorted(diags, key=lambda d: (d["tool"], d["key"], d["file"], int(d["line"]))):
            f.write("\t".join(str(d[c]).replace("\t", " ") for c in cols) + "\n")

    counts = collections.Counter((d["tool"], d["key"]) for d in diags)
    with open(os.path.join(out, "counts.tsv"), "w", encoding="utf-8") as f:
        f.write("tool\tkey\tcount\n")
        for (tool, key), n in sorted(counts.items(), key=lambda kv: (kv[0][0], -kv[1], kv[0][1])):
            f.write(f"{tool}\t{key}\t{n}\n")

    meta = {}
    meta_path = os.path.join(out, "meta.tsv")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = dict(l.rstrip("\n").split("\t", 1) for l in f if "\t" in l)
    eisop = [d for d in diags if d["tool"] == "eisop"]
    anomalies = [d for d in eisop if d["scope"] == "unmarked"]
    location = sum(1 for d in eisop if d["key"].startswith("jspecify.unrecognized.location"))
    injected = sum(1 for l in open(os.path.join(out, "build.log"), errors="replace")
                   if l.startswith("[eisop] "))

    with open(os.path.join(out, "summary.md"), "w", encoding="utf-8") as f:
        f.write(f"# {meta.get('project', '?')} / {meta.get('arm', '?')}\n\n")
        for k in ("sha", "args", "eisop_version", "java_home", "gradle_exit"):
            f.write(f"- {k}: `{meta.get(k, '?')}`\n")
        f.write(f"- compile tasks the checker was injected into: {injected}\n")
        f.write(f"- @NullMarked packages: {len(marked_dirs)}; class-level marked/unmarked files: "
                f"{len(marked_files)}; NullAway suppression sites: {len(suppressions)}\n")
        f.write(f"- EISOP diagnostics: {len(eisop)} ({location} jspecify.unrecognized.location.*)\n")
        f.write(f"- NullAway diagnostics: {sum(1 for d in diags if d['tool'] == 'nullaway')}\n")
        f.write(f"- crash lines: {len(crashes)}; compiler errors not tied to a file: {len(unanchored)}\n")
        f.write(f"- EISOP diagnostics in unmarked files (scoping anomalies): {len(anomalies)}\n")
        for where, expect in (("marked", "reported"), ("unmarked", "not reported")):
            tools = ", ".join(sorted(canary_hits[where])) or "none"
            f.write(f"- {where} canary (expect EISOP {expect}): tools reporting it: {tools}\n")
        f.write("\n")
        f.write("| tool | key | count |\n|---|---|---|\n")
        for (tool, key), n in sorted(counts.items(), key=lambda kv: (kv[0][0], -kv[1], kv[0][1])):
            f.write(f"| {tool} | `{key}` | {n} |\n")
        if crashes:
            f.write("\n## Crash lines\n\n```\n" + "\n".join(crashes[:20]) + "\n```\n")
        if unanchored:
            f.write("\n## Compiler errors not tied to a file\n\n```\n" + "\n".join(unanchored[:20]) + "\n```\n")
    with open(os.path.join(out, "summary.md"), encoding="utf-8") as f:
        sys.stdout.write(f.read())
    if injected == 0:
        print("WARNING: the checker was not injected into any compile task", file=sys.stderr)
    failed = False
    if "eisop" not in canary_hits["marked"] or "eisop" in canary_hits["unmarked"]:
        print("WARNING: canary check failed; this arm's counts are not trustworthy", file=sys.stderr)
        failed = True
    if crashes or unanchored:
        # A crash also stops checking the rest of its compilation unit, so counts undercount.
        print("WARNING: the checker crashed or failed; counts undercount", file=sys.stderr)
        failed = True
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
