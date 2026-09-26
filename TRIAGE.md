# Triage

Every EISOP (`-Amode=jspecify`) and NullAway finding in the corpus runs, sorted by cause.

`triage.py <src> <result-dir>` writes `triage.tsv`, one row per finding with its category. Rules
decide most findings; a short `REVIEWED` table in the script covers findings read by hand. The
results are from the runs in [STATUS.md](STATUS.md): EISOP 3.49.5-eisop2-SNAPSHOT, NullAway 0.14.1
and javac 25.

## Scope

- **reactor-pool and reactor-core: complete.** Both ran without a crash, and every one of their
  666 EISOP and 154 NullAway findings has a category.
- **context-propagation, caffeine, micrometer, junit-framework, spring-framework: partial.** The
  runs crashed.
  - **EISOP's side.** An EISOP crash costs EISOP only the rest of the crashing file. The findings
    it did emit are real output, and categories that depend only on EISOP's own message (`jdk:*`,
    `unspec:*`, `default:*`, `lint:*`, `jspecify:override-*`) apply to them as they are. Of their
    1,017 EISOP findings, 552 have a category and 465 are `untriaged`. Most of the remainder is in
    caffeine and spring-framework: dereferences, returns and inference failures that no rule
    covers.
  - **NullAway's side.** Error Prone skips every file compiled after the crash, and which files
    those are differs between machines. So `both:*`, and every `tools:*` row that requires NullAway
    to be silent nearby, are unreliable for these five projects.

  All five are to be rerun once EISOP has the crash fixes: the member-reference crash, and for
  junit-framework and spring-framework also the two inference crashes.

## Categories

The prefix says what the finding is. The verdict column says who is right under JSpecify:

- **EISOP FP:** EISOP reports something JSpecify does not make an error.
- **EISOP TP:** JSpecify does make it an error, whether or not NullAway reports it.
- **EISOP FN:** EISOP misses what JSpecify makes an error.

| category | what it is | verdict | evidence |
|---|---|---|---|
| `default:Void` | EISOP's `@Nullable` has `@DefaultFor(types = Void.class)`, so `Mono<Void>` fails a non-null bound, and inference, wildcard bounds and `@Nullable Void call()` overrides go wrong around it | EISOP FP | JSpecify has no `Void` rule; jspecify/jdk writes `CompletableFuture<@Nullable Void>` explicitly |
| `jdk:Objects.requireNonNull` | EISOP `requireNonNull(@NonNull T)`, JSpecify `requireNonNull(@Nullable T)` | EISOP FP | both JDK sources compared |
| `jdk:@Nullable parameter` | EISOP non-null, JSpecify `@Nullable Object`: `Map.get`/`remove`/`containsKey`, `Set`/`Collection.contains`/`remove`, `ConcurrentMap.remove`, `Method.invoke`, `Field.get`/`set`, `Array.set`, `LockSupport.unpark` | EISOP FP | both compared |
| `jdk:@PolyNull override` | an override of an EISOP `@PolyNull` method (`ConcurrentMap`); JSpecify `@Nullable` | EISOP FP | both compared |
| `jdk:Collection.toArray` | EISOP `@Nullable T[] toArray(@PolyNull T[])` and its `toarray.*` checks; JSpecify `T[] toArray(T[])` | EISOP FP | both compared |
| `jdk:Future<@Nullable ?>` | EISOP `Future<@Nullable ?> submit(Runnable)`, `ScheduledFuture<@Nullable ?> schedule*(Runnable)`; JSpecify `Future<?>` | EISOP FP | both compared |
| `jdk:ThreadLocal/AtomicReference<@Nullable T>` | EISOP `class ThreadLocal<@Nullable T>`, `AtomicReference<@Nullable V>` reject a subclass's non-null type argument; JSpecify `<T extends @Nullable Object>` | EISOP FP | both compared |
| `jdk:not @NullMarked in jspecify/jdk` | `FileNotFoundException(String)`, `UndeclaredThrowableException(Throwable)`: jspecify/jdk leaves these classes unmarked | EISOP FP | both compared |
| `jdk:@NonNull class Optional` | EISOP `public final @NonNull class Optional<T>` makes `@Nullable Optional` invalid | EISOP FP | both compared |
| `jdk:InvocationHandler.invoke` | EISOP `Object invoke(...)`, JSpecify `@Nullable Object invoke(...)` | EISOP FP | both compared |
| `jdk:@PolyNull Class.cast/System.getProperty/Optional.orElseGet` | NullAway only: EISOP `@PolyNull`, JSpecify `@Nullable`, so EISOP resolves to non-null | EISOP FN | both compared |
| `jdk:Collection.contains/remove` | NullAway only: JSpecify `contains(@Nullable Object)`, EISOP `contains(Object)`, so an override with a non-null parameter passes EISOP | EISOP FN | both compared |
| `unspec:reactive-streams`, `unspec:slf4j` | a call into a library with no nullness annotations: EISOP makes its parameters non-null, JSpecify leaves them unspecified, and NullAway accepts null | EISOP FP | `javap`: reactive-streams 1.0.4 and slf4j-api 1.7.36 have no nullness annotations |
| `unspec:java.xml/java.desktop` | overrides of, and calls into, `XMLStreamReader`, `Locator`, `XMLReader`, `PropertyEditorSupport`, `XMLEventFactory` | EISOP FP | jspecify/jdk has no java.xml or java.desktop sources |
| `unspec:@NullUnmarked spring asm` | overrides of `org.springframework.asm` visitors | EISOP FP | that package is `@NullUnmarked` |
| `tools:asserts` | an `assert x != null` precedes the use; both reactor projects set `NullAway:AssertsEnabled=true`, and EISOP ignores asserts without `-AassumeAssertionsAreEnabled` | configuration | build files |
| `tools:nullaway-suppressed` | inside `@SuppressWarnings` of `NullAway` or a name the project lists in `NullAway:SuppressionNameAliases` (`DataFlowIssue`, `NotNullFieldNotInitialized` in reactor), which EISOP does not honor; class-level suppressions are not detected | configuration | build files |
| `tools:raw-type` | a raw `Map.Entry` or `Callable`; the tools resolve raw type arguments differently | unspecified | source read |
| `tools:parameter-reassignment` | a `@Nullable` value assigned to a non-null parameter, including catch parameters; NullAway does not check assignments to locals or parameters | EISOP TP | source read |
| `tools:cast-of-nullable` | `(T) nullableValue`: EISOP reports the cast or a later use; NullAway reports the use with the operand's nullness, or nothing | EISOP TP | source read |
| `tools:wildcard-capture` | a capture of a wildcard with a nullable bound flows where a non-null type argument is required; NullAway does not check this | likely EISOP TP, not checked against the JSpecify reference checker | source read |
| `tools:method-purity` | `getX() != null ? getX().y() : …`; EISOP needs `@Pure`, NullAway assumes the getter returns the same value | EISOP FP in practice | source read: all 3 in reactor-core, 7 of 25 in spring |
| `tools:lambda-refinement`, `tools:field-refinement-after-call`, `tools:stream-filter-nonNull` | a null check EISOP does not carry into a lambda, past a method call, or through `filter(Objects::nonNull)` | EISOP FP in practice | source read |
| `tools:isEmpty-then-poll` | NullAway only: `poll()` after `!isEmpty()`, which EISOP's JDK refines | EISOP more precise | source read |
| `jspecify:override-type-parameter-bound` | an override of `<T extends @Nullable Object>` (`ExecutorService.submit`/`invokeAll`/`invokeAny`, `ScheduledExecutorService.schedule`, `Collection.toArray`) declares `<T>`, a non-null bound in `@NullMarked` code | TP | both JDKs declare the nullable bound |
| `jspecify:override-nullable-return` | `@Nullable T get()` and similar overriding `Supplier`/`Callable`/`Queue`/`Iterator`/`Function`/`Future` with a non-null type argument, or where NullAway reports it too | TP | both compared |
| `jspecify:override-non-null-parameter` | `equals(Object)`, `Map.get(Object)` and similar overridden with a non-null parameter | TP | both declare `@Nullable Object` |
| `jspecify:null-array-element`, `jspecify:null-argument` | `Disposable[] out = { null }`; `new TimedNode<>(-1, null, 0L)` for a non-null `T` | EISOP TP, NullAway FN | source read |
| `both:not-reviewed` | both tools report within two lines; not reviewed further | agreement | — |
| `lint:annotation-placement` | `type.anno.before.modifier` / `type.anno.before.decl.anno` style warnings | not nullness | — |
| `eisop-bug:inference-recovered` | `type.argument.inference.crashed`: EISOP caught an internal inference failure | EISOP bug | — |
| `eisop-inference:unexplained` | `type.arguments.not.inferred`, or a lambda return, where javac and NullAway infer; cause not determined | probably EISOP inference weakness | source read |

## Counts

| tool | category | reactor-pool | reactor-core | context-propagation* | caffeine* | micrometer* | junit-framework* | spring-framework* |
|---|---|---|---|---|---|---|---|---|
| eisop | `both:not-reviewed` |  | 92 |  |  | 4 | 54 | 27 |
| eisop | `default:Void` | 39 | 65 |  |  |  | 1 | 3 |
| eisop | `eisop-bug:inference-recovered` |  | 7 |  |  |  |  | 2 |
| eisop | `eisop-inference:unexplained` | 2 | 8 |  |  |  |  |  |
| eisop | `jdk:Objects.requireNonNull` |  | 14 |  | 59 |  | 21 | 8 |
| eisop | `jdk:@Nullable parameter` |  |  |  | 16 |  | 6 | 22 |
| eisop | `jdk:@PolyNull override` |  | 2 |  | 16 |  |  | 13 |
| eisop | `jdk:Collection.toArray` |  | 2 |  | 4 |  | 2 | 15 |
| eisop | `jdk:Future<@Nullable ?>` |  | 12 | 4 |  |  |  |  |
| eisop | `jdk:ThreadLocal/AtomicReference<@Nullable T>` |  | 3 | 1 |  | 1 | 2 | 6 |
| eisop | `jdk:not @NullMarked in jspecify/jdk` |  |  |  |  |  |  | 11 |
| eisop | `jdk:@NonNull class Optional` |  | 1 |  |  |  | 6 |  |
| eisop | `jdk:InvocationHandler.invoke` |  |  |  |  |  |  | 2 |
| eisop | `unspec:reactive-streams` |  | 83 |  |  |  |  |  |
| eisop | `unspec:slf4j` |  | 5 |  |  | 46 |  |  |
| eisop | `unspec:java.xml/java.desktop` |  |  |  |  |  |  | 26 |
| eisop | `unspec:@NullUnmarked spring asm` |  |  |  |  |  |  | 5 |
| eisop | `jspecify:override-type-parameter-bound` |  | 59 | 12 | 4 |  |  | 11 |
| eisop | `jspecify:override-non-null-parameter` |  | 6 |  |  |  | 38 | 2 |
| eisop | `jspecify:override-nullable-return` |  | 15 |  |  |  |  | 7 |
| eisop | `jspecify:null-array-element` |  | 2 |  |  |  |  |  |
| eisop | `jspecify:null-argument` |  | 1 |  |  |  |  |  |
| eisop | `lint:annotation-placement` |  | 22 |  |  |  | 5 | 2 |
| eisop | `tools:asserts` | 2 | 108 |  |  |  |  |  |
| eisop | `tools:nullaway-suppressed` | 1 | 38 |  | 26 | 2 |  | 16 |
| eisop | `tools:cast-of-nullable` |  | 13 |  | 9 |  | 1 | 8 |
| eisop | `tools:raw-type` |  | 30 |  |  |  |  |  |
| eisop | `tools:method-purity` |  | 3 |  |  |  |  | 25 |
| eisop | `tools:parameter-reassignment` |  | 16 |  |  |  | 1 |  |
| eisop | `tools:wildcard-capture` |  | 9 |  |  |  |  |  |
| eisop | `tools:lambda-refinement` |  | 4 |  |  |  |  |  |
| eisop | `tools:field-refinement-after-call` |  | 1 |  |  |  |  |  |
| eisop | `tools:stream-filter-nonNull` |  | 1 |  |  |  |  |  |
| eisop | `untriaged` |  |  | 5 | 95 | 11 | 77 | 277 |
| nullaway | `both:not-reviewed` |  | 81 |  |  | 4 | 52 | 24 |
| nullaway | `default:Void` |  | 7 |  |  |  |  |  |
| nullaway | `jdk:@PolyNull Class.cast/System.getProperty/Optional.orElseGet` |  | 8 |  |  |  | 4 |  |
| nullaway | `jdk:Collection.contains/remove` |  | 7 |  |  |  |  | 3 |
| nullaway | `jspecify:override-type-parameter-bound` |  | 23 | 6 |  |  |  |  |
| nullaway | `jspecify:override-nullable-return` |  | 12 |  |  |  |  | 4 |
| nullaway | `jspecify:override-non-null-parameter` |  | 5 |  |  |  | 7 | 1 |
| nullaway | `tools:cast-of-nullable` |  | 7 |  |  |  |  | 1 |
| nullaway | `tools:isEmpty-then-poll` | 1 | 2 |  |  |  | 2 |  |
| nullaway | `tools:raw-type` |  | 1 |  |  |  |  |  |
| nullaway | `untriaged` |  |  |  |  |  | 18 |  |
| eisop | total | 44 | 622 | 22 | 229 | 64 | 214 | 488 |
| nullaway | total | 1 | 153 | 6 | 0 | 4 | 83 | 33 |

\* crashed run: EISOP's rows are from the rules only, and rows that depend on NullAway's output (`both:*`, most `tools:*`) are unreliable; see Scope.

## What the complete projects say

reactor-core's 622 EISOP findings break down as follows:

| share | findings | kind | categories |
|---|---|---|---|
| 42% | 263 | not errors under JSpecify, or not nullness | unannotated libraries 88, `Void` 65, JDK-model differences 34, raw types 30, placement lint 22, EISOP inference 15 (7 recovered crashes), refinement EISOP loses 9 (purity 3, lambda 4, after a call 1, stream filter 1) |
| 23% | 146 | project configuration EISOP does not mirror | NullAway's `AssertsEnabled` 108, suppression aliases 38 |
| 28% | 175 | real, or agreed by both tools | 83 real under JSpecify (override type-parameter bounds 59, nullable returns 15, non-null parameters 6, null elements/arguments 3); 92 reported by both tools, not reviewed further |
| 6% | 38 | EISOP reports, NullAway does not check | parameter reassignment 16 and casts of nullable 13, both real under JSpecify; wildcard captures 9, likely real but not checked against the JSpecify reference checker |

reactor-pool's 44 are 39 `Void`, 2 asserts, 2 unexplained inference failures, and 1 suppressed.

NullAway's 154 findings over the two projects:

- 81 shared, and 1 raw `Callable` lambda returning null;
- 40 JSpecify override findings (type-parameter bounds 23, nullable returns 12, non-null parameters
  5), the same categories as EISOP's `jspecify:*` rows;
- 15 where EISOP's JDK uses `@PolyNull` or leaves `contains(Object)` unannotated;
- 7 `@Nullable Void call()` overrides;
- 7 casts;
- 3 `poll()` after `isEmpty()`.

## What would move the numbers most

Measured on the two complete projects (666 EISOP findings):

1. **No `Void` default under `-Amode=jspecify`:** 104 findings (16%).
2. **Mirror NullAway's configuration in the corpus run:** pass `-AassumeAssertionsAreEnabled` when a
   project sets `NullAway:AssertsEnabled` (110), and honor the project's NullAway suppression names
   (39). This is a harness change, not an EISOP change.
3. **Treat unannotated libraries as unspecified under the mode:** 88 here, plus micrometer's 46
   slf4j findings and spring's 31 in java.xml, java.desktop and its `@NullUnmarked` ASM copy.
4. **Align the annotated JDK with jspecify/jdk:** 34 here. Across all seven runs, even incomplete,
   the `jdk:*` categories add up to at least 249 EISOP findings; `requireNonNull` alone is 102.
5. **Inference:** 17 EISOP-side failures, 7 of them recovered crashes.
