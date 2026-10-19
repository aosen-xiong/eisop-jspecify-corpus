# Corpus status

Results of running `-Amode=jspecify` over the corpus, and open problems. How the corpus works is in
[README.md](README.md).

Last updated 2026-10-19, from CI run 39275479059: EISOP master `8449d975e0`
(`3.49.5-eisop2-SNAPSHOT`), JDK 25, NullAway 0.14.1. These results are the baselines in `baselines/`.

## Summary

Every Gradle project type-checks to the end with no crash: no build failure, and no caught
`type.argument.inference.crashed`. Every compiled root passes both canaries.

| project | revision | checked | EISOP | NullAway | locations: both / EISOP only / NullAway only |
|---|---|---|---|---|---|
| context-propagation | `6a9d15dc` | `:context-propagation` | 31 | 9 | 9 / 9 / 0 |
| reactor-pool | `6d40ec6e` | 2 modules | 44 | 1 | 0 / 43 / 1 |
| caffeine | `3afc2ec8` | `:caffeine` | 224 | 0 | 0 / 218 / 0 |
| graphql-java | `db17faea` | one project | 434 | 72 | 41 / 294 / 19 |
| junit-framework | `2e63847c` | 15 roots | 343 | 223 | 130 / 197 / 85 |
| reactor-core | `3775d11f` | `:reactor-core` | 940 | 153 | 114 / 739 / 31 |
| spring-boot | `ef67de05` | 2 modules | 538 | 161 | 114 / 357 / 28 |
| micrometer | `8a69589a` | 36 roots | 2301 | 102 | 81 / 683 / 13 |
| spring-framework | `6504e756` | 19 of 20 roots | 5411 | 1063 | 722 / 3919 / 233 |

Since September, the EISOP crashes that blocked context-propagation, caffeine, micrometer,
junit-framework and spring-framework are fixed (eisop#2098, #2155, #2156, #2158, #2159, #2160, #2163,
#2164, #2259), and bytecode storage is off under the mode (eisop#1305), which ended the Kotlin and
javac failures in spring-framework's `spring-test`.

## Where EISOP's findings come from

The same few causes account for most of the findings across projects. The counts are distinct
source lines in the baselines.

### Overrides of unannotated code (most of the 4,613 `override.*` findings)

Under `-Amode=jspecify`, code outside `@NullMarked`/`@AnnotatedFor` gets permissive defaults
(eisop#2150): its parameters and type-parameter bounds are `@Nullable`. That is lenient for a caller,
which may pass `null`, but strict for an override in `@NullMarked` code, whose unannotated parameter
is non-null. JSpecify calls such code unspecified, which is lenient both ways, and NullAway does not
report these. The largest groups, by overridden class:

| overridden class | findings | where |
|---|---|---|
| jOOQ `DefaultDSLContext` | 1667 | micrometer's `MetricsDSLContext`, one file; NullAway reports 2 there |
| reactive-streams `Subscriber` | 498 | reactor-core 458, spring-framework 36 |
| graphql-java's own unmarked `Instrumentation`, `GraphQLTypeVisitorStub`, `DataLoaderDispatchStrategy` | 183 | graphql-java, which marks only one package |
| Jackson `HandlerInstantiator`, AOP Alliance `MethodInterceptor`, Servlet `ServletContext`, Groovy `GroovyObject` | 224 | spring-framework |
| JDK classes eisop/jdk does not annotate (`XMLStreamWriter`, `PropertyEditorSupport`) | 80 | spring-framework |

These are an artifact of how the mode models unspecified nullness, not findings in the projects.

### Overrides that JSpecify's rules do reject

- **JDK generic methods (96 findings).** `ExecutorService.submit`, `invokeAll`, `schedule`, ...
  declare `<T extends @Nullable Object>`; context-propagation, reactor-core and micrometer override
  them with a plain `<T>`, which is non-null in `@NullMarked` code, and the parameter and return
  types built from `T` then mismatch too.
- **`equals(Object)` (98).** `Object.equals` takes `@Nullable Object` in both eisop/jdk and the
  JSpecify JDK; junit-framework (41), spring-boot (31), graphql-java (16) and others override it with
  an unannotated, so non-null, parameter.

### `Void` (eisop#2085)

checker-qual's `@Nullable` carries `@DefaultFor(types = Void.class)`, so every unannotated `Void` is
`@Nullable Void`, and the mode keeps that. reactor-core declares `Mono<T extends Object>` in a
`@NullMarked` package, so `Mono<Void>` breaks the bound. JSpecify gives `Void` no special treatment:
a non-null `Void` has no values, which is what `Mono<Void>` means. Of the 727
`type.arguments.not.inferred` findings, 257 are `@Nullable Void <: @NonNull Object` (spring-framework
222, reactor-core 17, reactor-pool 15), and 41 of reactor-pool's 44 findings mention `Void`. They are false
positives under JSpecify's rules, and no `Void` value flows through these `Mono`s. Dropping the
default under the mode would also make `return null` from a bare `Void` method an error in
`@NullMarked` code, which JSpecify requires but is a behavior change to decide deliberately.

### eisop/jdk disagreeing with the JSpecify JDK

- **`Objects.requireNonNull` (215):** caffeine 73, junit-framework 50, spring-framework 50,
  micrometer 24, reactor-core 17. eisop/jdk declares `requireNonNull(@NonNull T obj)`; the JSpecify
  JDK declares `requireNonNull(@Nullable T obj)`.
- **Collection lookups and removals** (`Map.remove`, `Set.contains`, ...): eisop/jdk's key parameter is
  non-null, the JSpecify JDK's `@Nullable`. In the other direction, JSpecify's nullable collection
  parameters produce some NullAway-only findings, such as reactor-core's `MpscLinkedQueue.java:198`.

### Not yet triaged

- **313 `type.arguments.not.inferred` with `capture of ? extends @Nullable Object <: @NonNull Object`**
  (spring-framework 257), and 157 with other constraints.
- **The plain nullness findings** (`argument.type.incompatible` 1,980, `dereference.of.nullable`
  1,077, `return.type.incompatible` 553), mostly in spring-framework. One likely cause: the projects
  tell NullAway about their own contract annotations (spring-framework passes
  `CustomContractAnnotations=org.springframework.lang.Contract`), so NullAway knows a value is
  non-null after an assertion helper, and EISOP does not read those annotations. Not checked.

### Lints, not nullness findings

89 `type.anno.before.*` (a type annotation written before a modifier or declaration annotation, as
reactor-core's `DelegateServiceScheduler` does with `@NonNull` above `@Override`), and 12
`jspecify.unrecognized.location.*` (graphql-java 7, spring-framework 5: annotations JSpecify gives no
meaning, such as spring-framework's `Function<@Nullable ? super K, @Nullable ? extends V>`).

## Projects

### context-propagation

Every main file is in a `@NullMarked` package. 9 locations are reported by both tools: 7 overrides
in `ContextExecutorService` and `ContextScheduledExecutorService` with a `<T>` where the JDK's is
nullable (up to 3 EISOP findings each), and 2 `previousValues.put(key, accessor.getValue())` calls in
`DefaultContextSnapshot` passing `@Nullable` to a `Map<Object, Object>`. The 9 EISOP-only locations
are 5 more overrides in the two executor services, `ContextRegistry.java:91`, `:92` and `:108`, and
`ContextSnapshot.java:136`. In September a runtime test of `ContextRegistry.java:108` and of the
`Map.put` calls found neither can fail: the library skips null values when capturing, and the map is
always a `HashMap`. A finding that is correct under JSpecify's rules is not necessarily a runtime bug.

### reactor-pool

41 of the 44 findings mention `Void` (the group above); 2 are `Subscriber` overrides. The 2
`assert x != null` findings at `SimpleDequePool.java:436` and `:444` from September are gone: the mode
now assumes assertions are enabled, as the project's NullAway does with `AssertsEnabled=true`. The 1
NullAway-only location is a dereference of `ref` at `SimpleDequePool.java:208`. The pinned revision depends on `reactor-core 3.8.8-SNAPSHOT`, which can
change between runs, and the project's JDK 21 toolchain is replaced with JDK 25.

### caffeine

The checked task compiles the named module `com.github.benmanes.caffeine`, with JDK 25 instead of
caffeine's JDK 26 (`--release 11`; JDK 26 gave identical findings). caffeine's own NullAway
configuration already sets `JSpecifyMode` and `JSpecifyExperimental` and checks every package through
`AnnotatedPackages`; it reports 0. EISOP's largest groups are `requireNonNull` (73) and `@PolyNull`
`ConcurrentMap` overrides such as `LocalCache.compute`, which JSpecify declares `@Nullable V`. Most
findings are in `BoundedLocalCache` (69), `LocalAsyncCache` (40) and `UnboundedLocalCache` (30).

### graphql-java

graphql-java marks one package `@NullMarked` and many classes individually, so its own unmarked
classes are unannotated code: 286 of the 434 findings are `override.param.invalid`, mostly overrides
of `Instrumentation`, `GraphQLTypeVisitorStub` and `DataLoaderDispatchStrategy`. The project pins
NullAway 0.13.8, which the corpus replaces with 0.14.1.

### junit-framework

All 15 roots compile. The project enables Gradle's Isolated Projects, which requires the
configuration cache the harness turns off, so the harness turns it off too. Besides the `equals` (41)
and `requireNonNull` (50) groups, the findings are spread over `junit-platform-engine` (75),
`junit-platform-commons` (65) and `junit-jupiter-engine` (38).

### reactor-core

The project's compilers are locked by its build before the harness can set them, so each task keeps
its own; `:reactor-core`'s is JDK 25. The project pins NullAway 0.13.7, which ignores
`JSpecifyExperimental` and reports 0; the corpus's 0.14.1 reports 153. 458 of the findings are
`Subscriber` overrides, and 22 are `type.anno.before.*` lints in `DelegateServiceScheduler`.

### spring-boot

Only `core:spring-boot` and `core:spring-boot-autoconfigure` (and what they depend on) are checked;
the other 247 roots are not requested.

### micrometer

All 36 roots compile. 1,672 of the 2,301 findings are in one file, `MetricsDSLContext`, which
overrides jOOQ's `DefaultDSLContext`; without it micrometer has 629.

### spring-framework

19 of 20 roots compile; `spring-aspects` is not run. NullAway is turned off for `spring-test`, where
it overflows the stack (uber/NullAway#1934), so NullAway reports the marked canary in 18 of the 19.
The largest modules are `spring-web` (985), `spring-test` (602), `spring-core` (582) and
`spring-context` (491).

## Other projects

- **Maven projects** (`spring-grpc`, `guava`) need an injection path that does not exist yet.
- **`eisop/guava` is not a corpus member.** It is EISOP's Checker Framework-annotated fork and has
  no `@NullMarked` packages; upstream `google/guava` is the JSpecify one.
