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

## reactor-pool

`reactor/reactor-pool` @ `6d40ec6e`, modules `reactor-pool` and `reactor-pool-micrometer`. The run
is clean: both canaries pass, nothing crashes, and its `diagnostics.tsv` is the baseline.

- **Moving dependency.** The pinned revision depends on `reactor-core 3.8.8-SNAPSHOT`, which can
  change between runs.
- **Toolchain.** The project pins a JDK 21 toolchain. The corpus compiles with JDK 25 instead, and
  JDK 21 gave identical findings here.

### Findings

EISOP 44, NullAway 1, at 44 locations: 0 reported by both tools, 43 by EISOP only, 1 by NullAway
only. All findings are in `reactor-pool`; `reactor-pool-micrometer` has none.

| group | EISOP | NullAway | cause |
|---|---|---|---|
| `Void` | 41 | 0 | EISOP's `@Nullable Void` default, which JSpecify does not have (below) |
| `assert x != null` (`SimpleDequePool.java:436`, `:444`) | 2 | 0 | settings: EISOP trusts asserts only with `-AassumeAssertionsAreEnabled`, which the mode does not set; the project's NullAway uses `AssertsEnabled=true` |
| lambda returning `null` (`SamplingAllocationStrategy.java:56`) | 1 | 0 | the tools agree: the project suppresses NullAway on this method |
| `e.poll()` inside `while (!e.isEmpty())` (`SimpleDequePool.java:207`) | 0 | 1 | EISOP is more precise: it knows `poll()` is non-null after the `isEmpty()` check, and JSpecify's JDK models make `poll()` nullable |

The project's other NullAway suppression, `@SuppressWarnings("NullAway.Init")` on a field
(`SimpleDequePool.java:760`), is silent in EISOP too, because the mode assumes initialization.

### The `Void` findings

The 41 findings are 21 `type.argument.type.incompatible` on `Mono<Void>`, 15
`type.arguments.not.inferred` (such as `Sinks.empty()` assigned to `Sinks.Empty<Void>`), and 5
`bound.type.incompatible` on `CoreSubscriber<? super Void>`.

- **EISOP:** checker-qual's `@Nullable` carries `@DefaultFor(types = Void.class)`, so every
  unannotated `Void` is `@Nullable Void`, and `-Amode=jspecify` does not change that. reactor-core
  declares `Mono<T extends Object>` in a `@NullMarked` package, so `Mono<@Nullable Void>` breaks
  the bound. A `Box<Void>` in a `@NullMarked` package reproduces it.
- **JSpecify:** an unannotated type in `@NullMarked` code excludes `null`, and `Void` gets no
  special treatment. A non-null `Void` has no values, which is what `Mono<Void>` means: the `Mono`
  completes or fails but never emits a value. Where a `null` really is delivered as a `Void`,
  JSpecify's own JDK models write it out, as in `CompletableFuture<@Nullable Void> runAsync(...)`.
  The JSpecify reference checker disables the `DefaultFor` defaulting, and NullAway reports none of
  these.

So the 41 are false positives under JSpecify's rules. No `Void` value flows through these
`Mono`s, so they are not runtime problems either way. Dropping the default under the mode would
remove them, but it would also make `return null` from a bare `Void` method an error in
`@NullMarked` code. JSpecify requires that, but it is a behavior change the fix has to decide
deliberately.

## caffeine

`ben-manes/caffeine` @ `3afc2ec8`, checked task `:caffeine:compileJava`, which compiles the named
module `com.github.benmanes.caffeine`. EISOP runs and passes the marked canary, but the run is
**blocked by the member-reference crash, so there is no baseline**.

- **The crash hits twice:** on `accessOrderWindowDeque()::…`, stopping EISOP at
  `BoundedLocalCache.java:3469`, and on `cache()::…`, stopping it at `LocalManualCache.java:110`.
- **Toolchain.** caffeine compiles with JDK 26 for `--release 11`. The corpus compiles with JDK 25;
  JDK 26 gave identical findings.
- **NullAway.** caffeine's own configuration already sets `JSpecifyMode` and
  `JSpecifyExperimental`, and checks every `com.github.benmanes.caffeine` package through
  `AnnotatedPackages`, which is wider than EISOP's `@NullMarked` scope. It reports 0 findings. The
  marked canary compiles after both crashes, and Error Prone skips files after a crash, so
  NullAway's side of the canary check cannot run here.

### Findings (incomplete: EISOP 229, NullAway 0)

| key | EISOP |
|---|---|
| `argument.type.incompatible` | 115 |
| `return.type.incompatible` | 33 |
| `override.return.invalid` | 17 |
| `type.arguments.not.inferred` | 14 |
| `assignment.type.incompatible` | 9 |
| `cast.unsafe` | 9 |
| other keys (8) | 32 |

Most are in `BoundedLocalCache` (70), `LocalAsyncCache` (40) and `UnboundedLocalCache` (30).

### Where they come from (first pass, not a full triage)

- **EISOP's annotated JDK, which disagrees with JSpecify's JDK models:**
  - **59 `Objects.requireNonNull` calls** on a possibly-null `V`. EISOP declares
    `requireNonNull(@NonNull T obj)`; JSpecify's models declare `requireNonNull(@Nullable T obj)`.
  - **About 15 collection lookups and removals** (`ConcurrentMap.remove` 6, `Map.remove` 4,
    `Set.remove` 2, `Map.get` 2, `Set.contains` 1). EISOP leaves the key parameter unannotated, so
    it is non-null; JSpecify's models declare `Map.remove(@Nullable Object key)`. The other
    methods are assumed to follow the same convention but were not checked individually.
  - **At least 15 override findings that require `@PolyNull`,** such as `LocalCache.compute`
    returning `@Nullable V` against EISOP's `@PolyNull V ConcurrentMap.compute(...)`. JSpecify's
    models declare `@Nullable V compute(...)`.
- **The rest,** about 140 findings, are not yet triaged.
- **NullAway suppressions as an oracle.** caffeine's main code has 27 NullAway suppressions, and
  EISOP reports within 15 lines of 22 of them. This is a rough proximity check, not an exact match.

## micrometer

`micrometer-metrics/micrometer` @ `8a69589a`. The run is **blocked by the member-reference crash,
and the crash stops most of the build**.

- **The crash** hits `micrometer-observation` on
  `InternalLoggerFactory.getInstance(ObservationTextPublisher.class)::info`
  (`ObservationTextPublisher.java:43`). A crash is a javac error, so that module's compile fails,
  and every module depending on it never compiles.
- **Coverage.** Of 36 source roots with `@NullMarked` packages, 2 compiled: `micrometer-commons`
  fully, and `micrometer-observation` up to the crash. `micrometer-core` and every registry did not
  compile. EISOP reported the marked canary in both compiled roots.

### Findings (incomplete: EISOP 64, NullAway 4)

49 locations: 3 reported by both tools, 46 by EISOP only, 0 by NullAway only. EISOP's findings are
51 in `micrometer-commons` and 13 in `micrometer-observation`.

- **Calls into SLF4J, which is not JSpecify-annotated (46 of 54 `argument.type.incompatible`).**
  micrometer's logging adapters pass `@Nullable` arguments to `org.slf4j.helpers.MessageFormatter`
  (20), `org.slf4j.Logger` methods (20) and `org.slf4j.spi.LocationAwareLogger.log` (6). Under
  `-Amode=jspecify`, EISOP treats an unannotated library's parameters as non-null. JSpecify calls
  them unspecified, and NullAway treats them as accepting null. This is the unspecified-nullness
  difference that jspecify.dev names as EISOP's main conformance gap.
- **A null-checked field used after a method call (4 `dereference.of.nullable`).**
  `SimpleObservation.java:151-175` checks `this.convention != null`, calls
  `this.context.add…(...)`, then uses `convention`. EISOP assumes the call might reset the field;
  NullAway assumes it does not. EISOP is the more cautious one, and JSpecify does not specify
  dataflow.
- **Both tools report 3 locations:** `AnnotationHandler.java:182`, `JdkLogger.java:77` and
  `ObservationRegistry.java:204`, all passing a `@Nullable` value to a non-null parameter.
- **The rest** (10 findings) are not yet triaged.

## reactor-core

`reactor/reactor-core` @ `3775d11f`, checked task `:reactor-core:compileJava`. The run is clean:
the build succeeds, the canary passes, and its `diagnostics.tsv` is the baseline. The
member-reference crash does not occur here.

- **Compiler.** Every compile task's compiler is already locked by the project's own build before
  the corpus can set it, so each keeps the project's compiler; for `:reactor-core` that is JDK 25.
- **NullAway version.** The project pins NullAway 0.13.7, which predates `JSpecifyExperimental`:
  the option is not in its jar, so that version silently ignores it and reports 0 findings. The
  corpus pins NullAway 0.14.1 everywhere, which reports 153 here. EISOP's findings are the same
  under either.

### Findings (EISOP 622, NullAway 153)

570 locations: 113 reported by both tools, 425 by EISOP only, 32 by NullAway only.

- **NullAway 0.14.1's findings** are mostly nullable arguments (43), generic inference failures
  (30), `ExecutorService`/`Collection` override bounds (23), and override return or parameter
  mismatches (30).
- **NullAway-only locations (32)** are 9 nullable arguments; 7 non-null parameters where the
  overridden method's parameter is nullable (such as `MpscLinkedQueue.java:198`); 6 nullable
  returns where the overridden method's return is non-null (such as `MonoRunnable.java:68`); and 10
  others (dereferences, unboxing, returns, inference). The overridden-parameter group is the
  reverse of caffeine's `Map.remove` findings: JSpecify's JDK models give collection methods
  nullable parameters where EISOP's JDK does not. That reading is not checked finding by finding.

| key | EISOP |
|---|---|
| `argument.type.incompatible` | 238 |
| `dereference.of.nullable` | 90 |
| `type.arguments.not.inferred` | 51 |
| `type.argument.type.incompatible` | 45 |
| `override.return.invalid` | 42 |
| `override.param.invalid` | 29 |
| `assignment.type.incompatible` | 27 |
| `override.typaram.invalid` | 23 |
| other keys (13) | 77 |

### Where they come from (first pass; the groups overlap)

- **reactive-streams, which is not JSpecify-annotated (104 findings).** 72 `Subscriber.onNext` and
  32 `Subscriber.onError` arguments. A type variable bounded `@Nullable` is passed to a
  `Subscriber<? super O>` from `org.reactivestreams` 1.0.4, whose wildcard capture EISOP gives a
  non-null bound. This is unspecified nullness again, combined with wildcards.
- **`ExecutorService` and `ScheduledExecutorService` overrides.** Most of the 94 override findings
  are on `submit` (21), `invokeAll` (18), `schedule` (12) and `invokeAny` (12): overrides written
  `<T>` in `@NullMarked` code, where the JDK's `T` is nullable. This is the pattern
  context-propagation shows, and NullAway 0.14.1 reports 21 of these overrides here too.
- **`Void` (70 findings mention it)**, as in reactor-pool.
- **`Objects.requireNonNull` (14)**, as in caffeine.
- **Annotation placement (22 `type.anno.before.*`).** `DelegateServiceScheduler` writes JSpecify's
  `@NonNull` above `@Override` on 11 methods, and EISOP asks for it immediately before the type.
  This is a style lint, not a nullness finding.
- **7 type-inference failures EISOP recovered from** (`type.argument.inference.crashed`), all
  lambdas assigned to raw functional types, such as
  `Supplier ZERO_SUPPLIER = () -> Hooks.wrapQueue(new ZeroQueue<>())` in `Queues.java` and
  `Function NEVER = e -> Flux.never()` in `MonoTimeout.java`: *"False bound … INFERENCE FAILED"*.
  EISOP reports these as warnings and keeps checking; they are EISOP bugs.
- **The rest are not yet triaged.** The largest files are `DelegateServiceScheduler` (48),
  `Context` (34), `BoundedElasticScheduler` (28), `Mono` (27) and
  `DelegatingScheduledExecutorService` (23).

## junit-framework

`junit-team/junit-framework` @ `2e63847c`. The run is **blocked by the member-reference crash**.

- **Isolated Projects.** The project enables Gradle's Isolated Projects, which requires the
  configuration cache the harness turns off, so the harness turns Isolated Projects off too.
- **The crash hits twice,** both times on a string-literal qualifier: `"(%s)"::formatted` in
  `junit-platform-engine` (`CompositeFilter.java:84`) and another in `junit-jupiter-params`
  (`ResolverFacade.java:426`). Both compiles fail, so the modules that depend on them, such as
  `junit-jupiter-engine` and `junit-platform-launcher`, never compile.
- **Coverage.** 7 of 15 source roots with `@NullMarked` packages compiled, and EISOP reported the
  marked canary in all 7. NullAway reported it in 5; the other 2 compiled after a crash.

### Findings (incomplete: EISOP 214, NullAway 83)

225 locations: 56 reported by both tools, 145 by EISOP only, 24 by NullAway only. EISOP's findings
are mostly in `junit-platform-engine` (76), `junit-platform-commons` (70) and `junit-jupiter-api`
(34).

- **`equals(Object)` overrides (38 `override.param.invalid`).** junit declares `equals(Object obj)`
  in `@NullMarked` code, which makes the parameter non-null. Both EISOP's JDK and JSpecify's JDK
  models declare `Object.equals(@Nullable Object obj)`, and an override may not narrow a parameter
  to non-null, so these are findings under JSpecify's rules, not an EISOP-specific artifact.
  NullAway reports 7 of the 38, with the same reason; why it misses the other 31 is not checked.
- **`Objects.requireNonNull` (20 of 71 `argument.type.incompatible`)**, as in caffeine: EISOP's
  JDK declares a non-null parameter, JSpecify's models a nullable one.
- **The rest are not yet triaged.**

## spring-framework

`spring-projects/spring-framework` @ `6504e756`. The run is **blocked: `spring-core` fails on
three EISOP crashes**, and every other module with `@NullMarked` code depends on `spring-core`, so
only `spring-core` was checked, and only partly. EISOP reported its marked canary.

### The crashes

| crash | where | minimal repro |
|---|---|---|
| member reference with a method-call qualifier | `NettyDataBuffer.java:82`, `predicate.negate()::test` | see context-propagation |
| `DefaultTypeHierarchy: unexpected combination` of an intersection and an array type | `ByteArrayEncoder.java:56`, `Flux.from(inputStream).map((byte[] bytes) -> ...)` with a `Publisher<? extends byte[]>` | a `from(Pub<? extends T>)` then `map((byte[] b) -> b.length)` on a `Pub<? extends byte[]>`; an implicit parameter `b -> b.length` does not crash |
| `AsSuperVisitor: type is not an erased subtype of supertype` | `MergedAnnotationCollectors.java:99`, `Collector.of(ArrayList::new, ..., list -> list.toArray(generator.apply(list.size())))` | the same `Collector.of` shape with an `IntFunction<R[]>` generator, whether the combiner is a generic method reference or a lambda |

The two new crashes are **not specific to `-Amode=jspecify`**: both repros also crash under the
plain Nullness Checker and under `-AonlyAnnotatedFor` alone.

### Findings from `spring-core` (incomplete: EISOP 488, NullAway 33)

- **The location check fires for the first time in the corpus:** 4
  `jspecify.unrecognized.location.wildcard` findings in `ConcurrentReferenceHashMap.java:373` and
  `:399`, which write `Function<@Nullable ? super K, @Nullable ? extends V>`, annotating the
  wildcards themselves where JSpecify gives the annotation no meaning.
- **2 type-inference failures EISOP recovered from** (`type.argument.inference.crashed`), at
  `AbstractCharSequenceDecoder.java:107` (`Mono.defer`) and `ExecutableHint.java:100`
  (`Comparator.thenComparing`).
- The largest keys are `argument.type.incompatible` (178), `dereference.of.nullable` (111),
  `type.arguments.not.inferred` (43) and `override.return.invalid` (42). They are not yet triaged.

## Other projects

- **Gradle projects** in `corpus.tsv` are `untried`, and CI runs them only when named explicitly.
  Their builds may need per-project tasks or flags before their numbers mean anything.
- **Maven projects** (`spring-grpc`, `guava`) need an injection path that does not exist yet.
- **`eisop/guava` is not a corpus member.** It is EISOP's Checker Framework-annotated fork and has
  no `@NullMarked` packages; upstream `google/guava` is the JSpecify one.
