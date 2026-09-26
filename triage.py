#!/usr/bin/env python3
"""Assigns every EISOP and NullAway finding of a project run a triage category.

usage: triage.py <project-source-dir> <result-dir>

Reads the run's build.log (the diagnostics plus the found/required/override detail that
diagnostics.tsv drops) and writes triage.tsv, one row per finding.  Categories come from RULES, an
ordered list; the first rule that matches a finding decides it, and a finding no rule matches is
"untriaged".  A rule may only claim a cause that has been checked; see TRIAGE.md for the evidence
behind each one.
"""

import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from summarize import DIAG, tool_of  # noqa: E402

BLOCK_END = re.compile(r"^(> Task |\[eisop|[0-9]+ (warning|error)s?$|BUILD |FAILURE|\* )")
PARAM_OF = re.compile(r"for parameter \S+ of (?P<target>.+?)\.$")


def parse(src, log_path):
    """Returns the findings in log_path as dicts, in log order, without canaries or duplicates."""
    findings, seen, current = [], set(), None
    with open(log_path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = DIAG.match(line)
            if m or BLOCK_END.match(line) or line.startswith("error: "):
                current = None
            if not m:
                if current is not None:
                    current["block"].append(line)
                continue
            if m.group("file").endswith("/EisopCorpusCanary.java"):
                continue
            path = os.path.realpath(m.group("file"))
            ident = (path, m.group("line"), m.group("key"), m.group("msg"))
            if ident in seen:
                continue
            seen.add(ident)
            current = {
                "tool": tool_of(m.group("key")),
                "key": m.group("key"),
                "file": os.path.relpath(path, src),
                "line": m.group("line"),
                "msg": m.group("msg"),
                "block": [],
            }
            findings.append(current)
    for d in findings:
        block = d.pop("block")
        d["source"] = block[0].strip() if block else ""
        d["found"] = next((b.split(":", 1)[1].strip() for b in block if b.startswith("  found   :")), "")
        d["required"] = next((b.split(":", 1)[1].strip() for b in block if b.startswith("  required:")), "")
        overridden = ""
        for i, b in enumerate(block):
            if b.strip().startswith("cannot override method in") and i + 1 < len(block):
                overridden = b.strip()[len("cannot override method in "):] + " :: " + block[i + 1].strip()
        d["overridden"] = overridden
        pm = PARAM_OF.search(d["msg"])
        d["target"] = pm.group("target") if pm else ""
    return findings


METHOD_SIGNATURE = re.compile(r"^\s*(?:[\w@]+\s+)*[\w<>\[\],.?@ ]+\s+\w+\s*\([^;]*$")
NOT_A_SIGNATURE = re.compile(r"^\s*(return|if|for|while|else|new|throw|catch|try|case)\b")
ASSERT_NON_NULL = re.compile(r"\bassert\s+\(?\s*([\w.]+)\s*!=\s*null")
# The distance, in lines, within which an assert or a paired finding of the other tool counts.
ASSERT_WINDOW = 30
PAIR_WINDOW = 2


class Finding:
    """A finding with access to its source file and to the other tool's findings in that file."""

    def __init__(self, d, lines, others):
        self.__dict__.update(d)
        self.lines = lines
        self.others = others
        self.text = " ".join((d["found"], d["required"], d["msg"], d["source"], d["overridden"]))

    def before(self, n):
        """The n source lines before this finding's line."""
        i = int(self.line) - 1
        return self.lines[max(0, i - n):i]

    def enclosing_signature(self):
        for l in reversed(self.before(40)):
            if METHOD_SIGNATURE.match(l) and not NOT_A_SIGNATURE.match(l):
                return l
        return ""

    def suppressed_for_nullaway(self, aliases):
        """Whether an @SuppressWarnings naming NullAway or one of the project's aliases for it
        covers this line: on the line, above it, or above the enclosing method.  Class-level
        suppressions are not seen."""
        names = "|".join(re.escape(a) for a in ("NullAway",) + tuple(aliases))
        pattern = re.compile(r'@SuppressWarnings\((?:[^)]*[{,\s(])?"(?:%s)(?::\w+)?"' % names)
        i = int(self.line) - 1
        windows = ["\n".join(self.lines[max(0, i - 4):i + 1])]
        signature = self.enclosing_signature()
        if signature:
            j = max(k for k in range(max(0, i - 40), i) if self.lines[k] == signature)
            windows.append("\n".join(self.lines[max(0, j - 4):j + 1]))
        return any(pattern.search(w) for w in windows)

    def assigns_parameter(self):
        m = re.match(r"\s*(\w+)\s*=[^=]", self.source)
        return bool(m) and re.search(r"[(,]\s*(?:final\s+)?[\w<>?,. \[\]@]+\s%s\s*[,)]" % m.group(1),
                                     self.enclosing_signature())

    def paired(self):
        """Whether the other tool reports within PAIR_WINDOW lines (a multi-line expression can put
        the two tools' findings on different lines)."""
        return any(abs(int(o["line"]) - int(self.line)) <= PAIR_WINDOW for o in self.others)

    def asserted_non_null(self):
        """Whether a preceding assert says something on this line is non-null."""
        names = set()
        for l in self.before(ASSERT_WINDOW):
            names.update(n[len("this."):] if n.startswith("this.") else n for n in ASSERT_NON_NULL.findall(l))
        if self.key == "dereference.of.nullable" or self.key == "iterating.over.nullable":
            name = self.msg.rsplit(" ", 1)[-1]
            return (name[len("this."):] if name.startswith("this.") else name) in names
        return any(re.search(r"(?<![\w])(?:this\.)?%s(?![\w(])" % re.escape(n), self.source) for n in names)


def eisop(*keys):
    return lambda f: f.tool == "eisop" and (not keys or f.key in keys)


def nullaway(f):
    return f.tool == "nullaway"


# Each rule is (category, predicate).  The first matching rule decides.  Categories are grouped by
# their prefix:
#   jdk:       EISOP's annotated JDK disagrees with JSpecify's JDK models (both files compared)
#   default:   an EISOP default JSpecify does not have
#   unspec:    an unannotated library, whose nullness JSpecify leaves unspecified
#   tools:     EISOP and NullAway analyze the same code differently
#   jspecify:  a finding under JSpecify's own rules, where both JDK models agree
#   both:      both tools report it, not reviewed further
#   lint:      not a nullness finding
#   eisop-bug: an internal EISOP failure
REACTIVE_STREAMS = ("Subscriber.", "Publisher.", "Subscription.", "Processor.")
# Set per project in main() from its build files.
SUPPRESSION_ALIASES = ()
RULES = [
    ("lint:annotation-placement", eisop("type.anno.before.modifier", "type.anno.before.decl.anno")),
    ("eisop-bug:inference-recovered", eisop("type.argument.inference.crashed")),
    # EISOP: @Nullable T[] toArray(@PolyNull T[] a); JSpecify: T[] toArray(T[] a).
    ("jdk:Collection.toArray",
     lambda f: eisop()(f) and (f.key.startswith("toarray.") or ".toArray(" in f.source) and not f.paired()),
    # EISOP: requireNonNull(@NonNull T obj); JSpecify: requireNonNull(@Nullable T obj).
    ("jdk:Objects.requireNonNull",
     lambda f: eisop("argument.type.incompatible")(f) and f.target.startswith("Objects.requireNonNull")
     and "@Nullable" in f.found),
    # EISOP: Future<@Nullable ?> submit(Runnable) and ScheduledFuture<@Nullable ?> schedule*(Runnable);
    # JSpecify: Future<?>, ScheduledFuture<?>.
    ("jdk:Future<@Nullable ?>", lambda f: eisop("override.return.invalid")(f) and "Future<@Nullable ?" in f.required),
    # EISOP: class ThreadLocal<@Nullable T>, class AtomicReference<@Nullable V>, which a subclass's
    # non-null type argument cannot satisfy; JSpecify: <T extends @Nullable Object>.
    ("jdk:ThreadLocal/AtomicReference<@Nullable T>",
     lambda f: eisop("type.argument.type.incompatible")(f)
     and re.search(r"of (ThreadLocal|AtomicReference)\.$", f.msg) and "super @Nullable NullType" in f.required),
    # EISOP: contains(Object o), remove(Object o); JSpecify: contains(@Nullable Object o), so NullAway
    # rejects an override with a non-null parameter and EISOP accepts it.
    ("jdk:Collection.contains/remove",
     lambda f: nullaway(f) and re.search(r"(Abstract)?Collection\.(contains|remove)\(java\.lang\.Object\)", f.msg)),
    # EISOP: a non-null parameter; JSpecify: @Nullable Object.  Map.get/remove/containsKey(key),
    # Set.contains/remove, Collection.contains/remove, ConcurrentMap.remove(key, value),
    # Method.invoke(obj, args), Field.get(obj)/set(obj, value), Array.set(array, i, value),
    # LockSupport.unpark(thread).
    ("jdk:@Nullable parameter",
     lambda f: eisop("argument.type.incompatible")(f) and "@Nullable" in f.found and re.match(
         r"(Map|HashMap|ConcurrentMap|ConcurrentHashMap|Set|Collection|List)\.(get|remove|containsKey|contains)$"
         r"|Method\.invoke$|Field\.(get|set)$|Array\.set$|LockSupport\.unpark$", f.target.split("(")[0])),
    # jspecify/jdk leaves these classes outside @NullMarked, so their parameters are unspecified.
    ("jdk:not @NullMarked in jspecify/jdk",
     lambda f: eisop("argument.type.incompatible")(f)
     and re.match(r"(FileNotFoundException|UndeclaredThrowableException) constructor$", f.target)),
    # jspecify/jdk has no model of java.xml or java.desktop; InvocationHandler.invoke returns
    # @Nullable Object in jspecify/jdk and Object in EISOP.
    ("unspec:java.xml/java.desktop",
     lambda f: (eisop("override.return.invalid", "override.param.invalid")(f) and re.match(
         r"@NonNull (XMLStreamReader|XMLEventReader|XMLReader|Locator2?|PropertyEditorSupport)\b", f.overridden))
     or (eisop("argument.type.incompatible")(f) and f.target.startswith("XMLEventFactory."))),
    ("jdk:InvocationHandler.invoke",
     lambda f: eisop("override.return.invalid")(f) and f.overridden.startswith("@NonNull InvocationHandler")),
    # EISOP: public final @NonNull class Optional<T>, so @Nullable Optional is an invalid type;
    # JSpecify: public final class Optional<T>.
    ("jdk:@NonNull class Optional",
     lambda f: eisop("type.invalid.annotations.on.use")(f) and f.msg.endswith("type java.util.Optional")),
    # EISOP: @PolyNull T cast(@PolyNull Object), @PolyNull String getProperty(String, @PolyNull String),
    # @PolyNull T orElseGet(Supplier<? extends @PolyNull T>); JSpecify: @Nullable in each, so NullAway
    # reports what EISOP resolves to non-null.
    ("jdk:@PolyNull Class.cast/System.getProperty/Optional.orElseGet",
     lambda f: nullaway(f) and re.search(r"::cast\b|System\.getProperty\([^()]*,|orElseGet\(",
                                         f.source + " " + f.msg + " " + " ".join(f.before(3)))),
    # EISOP's @Nullable has @DefaultFor(types = Void.class); JSpecify has no such default.
    ("default:Void",
     lambda f: not f.paired() and ("Void" in f.text or (
         f.key in ("type.arguments.not.inferred", "bound.type.incompatible")
         and ("Void" in f.enclosing_signature() or any("Void>" in l for l in f.before(2)))))),
    ("default:Void", lambda f: nullaway(f) and "Callable.call()" in f.msg and "Void" in f.source),
    # The project suppresses NullAway here under one of its SuppressionNameAliases; EISOP does not
    # honor those names.
    ("tools:nullaway-suppressed", lambda f: eisop()(f) and f.suppressed_for_nullaway(SUPPRESSION_ALIASES)),
    ("unspec:reactive-streams",
     lambda f: eisop()(f) and f.target.startswith(REACTIVE_STREAMS) and not f.paired()),
    # slf4j-api 1.7.36 (reactor-core, micrometer) has no nullness annotations.
    ("unspec:slf4j",
     lambda f: eisop("argument.type.incompatible")(f) and (
         f.target.startswith(("MessageFormatter.", "LocationAwareLogger."))
         or (f.target.startswith("Logger.") and any("org.slf4j" in l for l in f.lines)
             and f.source.lstrip().startswith("logger.")
             and not any("java.util.logging.Logger logger" in l for l in f.before(int(f.line)))))),
    # org.springframework.asm is @NullUnmarked in spring-core.
    ("unspec:@NullUnmarked spring asm",
     lambda f: eisop("override.return.invalid", "override.param.invalid")(f)
     and re.match(r"@NonNull (AnnotationVisitor|ClassVisitor|MethodVisitor|FieldVisitor)\b", f.overridden)),
    # NullAway does not check assignments to locals or parameters; a parameter's declared type is
    # non-null under JSpecify.
    ("tools:parameter-reassignment",
     lambda f: eisop("assignment.type.incompatible")(f) and not f.paired() and f.assigns_parameter()),
    # NullAway does not check casts, and treats a cast's result like its operand.
    ("tools:cast-of-nullable", lambda f: eisop("cast.unsafe")(f) and not f.paired() and "@Nullable" in f.msg),
    ("tools:cast-of-nullable",
     lambda f: eisop("dereference.of.nullable")(f) and not f.paired() and any(
         re.search(r"\b%s\s*=\s*\([\w<>?, .]+\)\s*\w+;" % re.escape(f.msg.rsplit(" ", 1)[-1]), l)
         for l in f.before(3))),
    ("tools:cast-of-nullable",
     lambda f: nullaway(f) and re.match(r"passing @Nullable parameter '(\w+)'", f.msg) and any(
         re.search(r"\b%s\s*=\s*\([\w<>?, .]+\)\s*\w+;" % re.match(r"passing @Nullable parameter '(\w+)'", f.msg).group(1), l)
         for l in f.before(ASSERT_WINDOW * 3))),
    # NullAway's AssertsEnabled=true lets an assert refine; EISOP needs -AassumeAssertionsAreEnabled.
    ("tools:asserts", lambda f: eisop()(f) and not f.paired() and f.asserted_non_null()),
    # NullAway treats repeated calls of the same getter as the same value; EISOP needs @Pure.
    ("tools:method-purity",
     lambda f: eisop("dereference.of.nullable")(f) and f.msg.endswith("()")
     and (f.msg.rsplit(" ", 1)[-1] + " != null") in " ".join(f.before(1) + [f.source])),
    # EISOP does not carry a field's null check into a lambda body.
    ("tools:lambda-refinement",
     lambda f: eisop("dereference.of.nullable")(f) and re.search(
         r"\b%s\s*!=\s*null\s*\?.*->" % re.escape(f.msg.rsplit(" ", 1)[-1]), f.source)),
    # EISOP's Queue.isEmpty() refines poll(); NullAway does not.
    ("tools:isEmpty-then-poll",
     lambda f: nullaway(f) and "dereferenced expression" in f.msg and any("isEmpty()" in l for l in f.before(15))),
    # Both JDK models declare <T extends @Nullable Object>; the override declares a non-null bound.
    # Only the JDK types whose declarations were compared on both sides.
    ("jspecify:override-type-parameter-bound",
     lambda f: (eisop("override.typaram.invalid", "override.return.invalid", "override.param.invalid")(f)
                and "extends @NonNull Object" in f.found
                and re.search(r"extends @Nullable Object", f.required)
                and re.match(r"@NonNull (ExecutorService|ScheduledExecutorService|ScheduledThreadPoolExecutor"
                             r"|AbstractExecutorService|Collection)\b", f.overridden))
     or (nullaway(f) and "non-null upper bound" in f.msg)),
    # The same shape over a library with no JSpecify annotations (jOOQ 3.14.16, grpc-api 1.84, both
    # checked: no @NullMarked): its bounds are unspecified, so the override is not an error.
    ("unspec:override of unannotated library bound",
     lambda f: eisop("override.typaram.invalid", "override.return.invalid", "override.param.invalid")(f)
     and re.match(r"@NonNull (DefaultDSLContext|ServerInterceptor|ClientInterceptor)\b", f.overridden)),
    # EISOP: @PolyNull V compute(...) and similar in ConcurrentMap; JSpecify: @Nullable V.
    ("jdk:@PolyNull override", lambda f: eisop("override.return.invalid", "override.param.invalid")(f)
     and "@PolyNull" in f.required and "@PolyNull" not in f.found),
    # A @Nullable return overriding a type-variable return whose JSpecify JDK model was compared, or
    # one NullAway reports too.  Overrides of other library types (java.xml, ASM) are not claimed here.
    ("jspecify:override-nullable-return",
     lambda f: (eisop("override.return.invalid")(f) and "Nullable " in f.found.split(" extends")[0]
                and "Nullable " not in f.required.split(" extends")[0]
                and (f.paired() or re.match(r"@NonNull (Supplier|Callable|Queue|Iterator|BiFunction|Function|Future)<",
                                            f.overridden)))
     or (nullaway(f) and f.msg.startswith("method returns @Nullable, but superclass method"))),
    ("jspecify:override-non-null-parameter",
     lambda f: (eisop("override.param.invalid")(f) and f.found.startswith("@NonNull")
                and f.required.startswith("@Nullable"))
     or (nullaway(f) and re.search(r"is @NonNull, but parameter in superclass method .* is @Nullable", f.msg))),
    ("both:not-reviewed", lambda f: f.paired()),
]

# Findings no rule decides, reviewed by hand: (file suffix, first line, last line, key) -> category.
# The reason is in TRIAGE.md under the category.
REVIEWED = {
    # An assert of the same local further up than ASSERT_WINDOW, with no reassignment in between on
    # that path.
    ("reactor/core/publisher/SinkManyEmitterProcessor.java", 454, 454, "dereference.of.nullable"): "tools:asserts",
    ("reactor/core/publisher/FluxWindowPredicate.java", 262, 268, "dereference.of.nullable"): "tools:asserts",
    ("reactor/core/publisher/FluxWindowTimeout.java", 640, 640, "dereference.of.nullable"): "tools:asserts",
    ("reactor/core/publisher/FluxWindowTimeout.java", 2030, 2030, "dereference.of.nullable"): "tools:asserts",
    # Map.Entry[] entries = map.entrySet().toArray(...); entries[i].getKey() on the raw Map.Entry is
    # @Nullable Object in both JDK models; NullAway does not check raw types.
    ("reactor/util/context/Context.java", 155, 173, "argument.type.incompatible"): "tools:raw-type",
    ("reactor/core/publisher/FluxGenerate.java", 47, 47, "NullAway"): "tools:raw-type",
    # A capture of a wildcard with a nullable bound flows where a non-null type argument is required;
    # NullAway's JSpecify mode does not check wildcard captures.
    ("reactor/util/context/Context.java", 298, 298, "argument.type.incompatible"): "tools:wildcard-capture",
    ("reactor/util/context/ContextN.java", 207, 207, "argument.type.incompatible"): "tools:wildcard-capture",
    ("reactor/core/publisher/Operators.java", 490, 490, "argument.type.incompatible"): "tools:wildcard-capture",
    ("reactor/core/publisher/Operators.java", 535, 535, "argument.type.incompatible"): "tools:wildcard-capture",
    ("reactor/core/publisher/FluxZip.java", 925, 925, "argument.type.incompatible"): "tools:wildcard-capture",
    ("reactor/core/publisher/Mono.java", 3252, 3252, "argument.type.incompatible"): "tools:wildcard-capture",
    ("reactor/core/publisher/FluxBufferBoundary.java", 72, 72, "argument.type.incompatible"): "tools:wildcard-capture",
    ("reactor/core/publisher/FluxBufferBoundary.java", 73, 73, "conditional.type.incompatible"): "tools:wildcard-capture",
    ("reactor/core/publisher/MonoWhen.java", 139, 139, "bound.type.incompatible"): "tools:wildcard-capture",
    # A catch parameter, or a parameter assigned inside a while condition.
    ("reactor/core/publisher/FluxZip.java", 910, 996, "assignment.type.incompatible"): "tools:parameter-reassignment",
    ("reactor/core/publisher/FluxCombineLatest.java", 450, 450, "assignment.type.incompatible"): "tools:parameter-reassignment",
    ("reactor/core/scheduler/BoundedElasticScheduler.java", 601, 601, "assignment.type.incompatible"): "tools:parameter-reassignment",
    # if (onOverflow == null) return; ... lambda -> onOverflow.accept(value), a final field.
    ("reactor/core/publisher/UnicastProcessor.java", 317, 317, "dereference.of.nullable"): "tools:lambda-refinement",
    # this.resources = new LinkedList<>(); a call; this.resources.add(d).
    ("reactor/core/Disposables.java", 141, 141, "dereference.of.nullable"): "tools:field-refinement-after-call",
    # Stream.of(array).filter(Objects::nonNull) returned as a stream of non-null elements.
    ("reactor/core/publisher/FluxFlatMap.java", 295, 295, "return.type.incompatible"): "tools:stream-filter-nonNull",
    # final Disposable[] out = { null }: a non-null element type, initialized with null.
    ("reactor/core/publisher/ConnectableFlux.java", 106, 106, "assignment.type.incompatible"): "jspecify:null-array-element",
    ("reactor/core/publisher/ConnectableFlux.java", 106, 106, "array.initializer.type.incompatible"): "jspecify:null-array-element",
    # TimedNode<T> h = new TimedNode<>(-1, null, 0L): null for a non-null T; NullAway misses it through
    # the diamond.
    ("reactor/core/publisher/FluxReplay.java", 176, 176, "argument.type.incompatible"): "jspecify:null-argument",
    # EISOP cannot infer type arguments that javac and NullAway infer; cause not determined.
    ("reactor/core/publisher/MonoHandleFuseable.java", 48, 48, "type.arguments.not.inferred"): "eisop-inference:unexplained",
    ("reactor/core/publisher/FluxHandleFuseable.java", 62, 62, "type.arguments.not.inferred"): "eisop-inference:unexplained",
    ("reactor/core/publisher/FluxHandle.java", 49, 49, "type.arguments.not.inferred"): "eisop-inference:unexplained",
    ("reactor/core/publisher/MonoHandle.java", 46, 46, "type.arguments.not.inferred"): "eisop-inference:unexplained",
    ("reactor/core/scheduler/SchedulerState.java", 44, 51, "type.arguments.not.inferred"): "eisop-inference:unexplained",
    ("reactor/core/publisher/CallSiteSupplierFactory.java", 57, 60, "return.type.incompatible"): "eisop-inference:unexplained",
    ("reactor/pool/decorators/GracefulShutdownInstrumentedPool.java", 69, 69, "type.arguments.not.inferred"): "eisop-inference:unexplained",
    ("reactor/pool/SimpleDequePool.java", 466, 466, "type.arguments.not.inferred"): "eisop-inference:unexplained",
}


def categorize(f):
    reviewed = next((v for (suffix, first, last, key), v in REVIEWED.items()
                     if f.file.endswith(suffix) and first <= int(f.line) <= last and f.key == key), None)
    if reviewed:
        return reviewed
    for category, predicate in RULES:
        if predicate(f):
            return category
    return "untriaged"


def suppression_aliases(src):
    """The NullAway:SuppressionNameAliases names any Gradle build file of the project sets."""
    aliases = set()
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in (".git", "build", "src", ".gradle")]
        for name in files:
            if name.endswith((".gradle", ".gradle.kts")):
                with open(os.path.join(root, name), encoding="utf-8", errors="replace") as f:
                    for m in re.finditer(r'SuppressionNameAliases"\s*,\s*"([^"]*)"', f.read()):
                        aliases.update(a.strip() for a in m.group(1).split(",") if a.strip())
    return tuple(sorted(aliases))


def main():
    global SUPPRESSION_ALIASES
    src, out = os.path.realpath(sys.argv[1]), sys.argv[2]
    SUPPRESSION_ALIASES = suppression_aliases(src)
    raw = [d for d in parse(src, os.path.join(out, "build.log")) if d["tool"] in ("eisop", "nullaway")]
    by_file = collections.defaultdict(list)
    for d in raw:
        by_file[(d["file"], d["tool"])].append(d)
    sources = {}
    findings = []
    for d in raw:
        if d["file"] not in sources:
            with open(os.path.join(src, d["file"]), encoding="utf-8", errors="replace") as f:
                sources[d["file"]] = f.read().split("\n")
        other = "nullaway" if d["tool"] == "eisop" else "eisop"
        findings.append(Finding(d, sources[d["file"]], by_file[(d["file"], other)]))
    cols = ["category", "tool", "key", "file", "line", "target", "found", "required", "overridden", "msg", "source"]
    with open(os.path.join(out, "triage.tsv"), "w", encoding="utf-8") as f:
        f.write("\t".join(cols) + "\n")
        for d in findings:
            d.category = categorize(d)
            f.write("\t".join(str(getattr(d, c)).replace("\t", " ") for c in cols) + "\n")
    counts = collections.Counter((d.tool, d.category) for d in findings)
    for (tool, category), n in sorted(counts.items(), key=lambda kv: (kv[0][0], -kv[1])):
        print(f"{tool}\t{category}\t{n}")


if __name__ == "__main__":
    main()
