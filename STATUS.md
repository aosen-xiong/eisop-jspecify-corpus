# Corpus status

Results of running `-Amode=jspecify` over the corpus, and open problems. How the corpus works is in
[README.md](README.md).

Last updated 2026-09-14, against EISOP `026312a` (`3.49.5-eisop2-SNAPSHOT`) on JDK 25.

## context-propagation

`micrometer-metrics/context-propagation` @ `6a9d15dc`. The run passes both canaries, but it is
**blocked by an EISOP crash, so there is no baseline**.

### The crash

EISOP's `-AjspecifyUnrecognizedLocations`, which `-Amode=jspecify` turns on, crashes on a method
reference whose qualifier is an expression rather than a name. No `@NullMarked` or JSpecify
annotation is needed:

```java
import java.util.function.Supplier;

class Repro {
    Supplier<Integer> s = "abc"::length;
}
```

```
error: TreeUtils.getExplicitAnnotationTrees: what typeTree? STRING_LITERAL ...
  at org.checkerframework.javacutil.TreeUtils.getExplicitAnnotationTrees(TreeUtils.java:2483)
  at ...NullnessNoInitAnnotatedTypeFactory.containsNullnessAnnotation(...:1038)
  at ...NullnessNoInitVisitor.checkJSpecifyLocation(...:397)
  at ...NullnessNoInitVisitor.visitMemberReference(...:514)
```

| qualifier | example | result |
|---|---|---|
| string literal | `"abc"::length` | crash |
| `new` expression | `new Object()::toString` | crash |
| method call | `make()::toString` | crash |
| variable | `o::toString` | ok |
| type name | `Object::toString` | ok |

In context-propagation the trigger is `capture()::wrap` at `ContextExecutorService.java:77`.

### What the crash does to the run

| | local (macOS) | CI (Linux) |
|---|---|---|
| EISOP | 22 findings: the rest of `ContextExecutorService.java` is skipped | 22, the same |
| NullAway | 6 findings: `DefaultContextSnapshot.java` and `ContextScheduledExecutorService.java` were compiled after the crashing file and skipped | 9: the crashing file was compiled last, so nothing was skipped |

Both comparisons are invalid, and they differ from each other.

### Expected result once the crash is fixed

Before the corpus settled on `-Amode=jspecify` alone, it also ran the mode's options without
`-AjspecifyUnrecognizedLocations`. That run did not crash. The location check reported nothing in
it, so turning the check back on should not add findings, and this is the expected result:

- **Counts:** EISOP 29, NullAway 9, at 16 locations: 9 reported by both tools, 7 by EISOP only,
  0 by NullAway only.
- **Both tools report:**
  - 7 overrides in `ContextExecutorService` and `ContextScheduledExecutorService` that give `<T>`
    a non-null bound where the JDK's is nullable. At those locations EISOP reports 19 findings,
    because one bad override bound produces up to 3 EISOP findings.
  - 2 `previousValues.put(key, accessor.getValue())` calls in `DefaultContextSnapshot`, passing a
    `@Nullable` value to a `Map<Object, Object>`.
- **EISOP only, from EISOP's annotated JDK, which disagrees with JSpecify's JDK models:**
  - 4 `Future<?>` / `ScheduledFuture<?>` overrides clash with EISOP's `Future<@Nullable ?>`;
    JSpecify's models declare `Future<?>`.
  - `ContextRegistry.java:91-92` clash with EISOP's `ThreadLocal<@Nullable T>`; JSpecify's models
    declare `ThreadLocal<T extends @Nullable Object>`. Line 92 involves inference, so its cause is
    likely but not certain.
- **EISOP only, the declared types break a rule, but nothing fails at runtime:**
  `ContextRegistry.java:108` passes a `V extends @Nullable Object` as the type argument of
  `ThreadLocalAccessor<V>`, whose `V` is non-null.

### Which findings can fail at runtime

None found so far. A runtime test of the `ContextRegistry.java:108` accessor went through capture,
set, and restore with the thread-local set and unset, with and without `clearMissing`. Its value
callback was never given `null`: the library skips null values when capturing and calls the
no-argument `restore()` for a null previous value. The `Map.put` findings cannot fail either: the
map is always a `HashMap`, which accepts `null`.

A finding that is correct under JSpecify's rules is not necessarily a runtime bug, so triage
should record the two separately.

### Caveat

The scoping-anomaly counter proves nothing on this project. All 13 main source files are in
`@NullMarked` packages, so it cannot fire; only the unmarked canary checks scoping here.

## Other projects

- **Gradle projects** in `corpus.tsv` are `untried`, and CI runs them only when named explicitly.
  Their builds may need per-project tasks or flags before their numbers mean anything.
- **Maven projects** (`spring-grpc`, `guava`) need an injection path that does not exist yet.
- **`eisop/guava` is not a corpus member.** It is EISOP's Checker Framework-annotated fork and has
  no `@NullMarked` packages; upstream `google/guava` is the JSpecify one.
