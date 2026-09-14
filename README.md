# EISOP JSpecify-mode corpus

Runs the EISOP Nullness Checker's `-Amode=jspecify` over pinned revisions of real
JSpecify-annotated projects that already check themselves with NullAway. It records what EISOP
reports inside their `@NullMarked` scope, and compares it with NullAway on the same code.

The projects need no edits. An init script, `eisop-nullness.init.gradle`, adds the checker to their
compile tasks, the same idea as NullAway's `compile-other-projects` CI job. There are two
differences. NullAway's job only swaps a version and checks that the build passes. This one also
adds the processor, and it records each diagnostic so runs can be compared against a baseline.

## Layout

| file | purpose |
|---|---|
| `corpus.tsv` | the projects: repo, pinned SHA, build system, compile tasks, JDK, status |
| `eisop-nullness.init.gradle` | injects the checker and sets its options and NullAway's; configured by `EISOP_VERSION` and `EISOP_TASKS` |
| `run-project.sh <name>` | clones at the pinned SHA, adds canaries, builds, summarizes, compares |
| `summarize.py` | `build.log` → `diagnostics.tsv`, `counts.tsv`, `summary.md` |
| `compare.py <diagnostics.tsv>` | pairs EISOP and NullAway findings by (file, line) into both / EISOP-only / NullAway-only → `comparison.md` |
| `diff.py <base> <new>` | compares two `diagnostics.tsv` by (tool, key, file, message), ignoring line shifts |
| `baselines/<project>/` | stored `diagnostics.tsv` that CI diffs against |

## Run setting

Each project is built once, with both tools in the same compile.

- **EISOP:** `-Amode=jspecify` and nothing else. It is the configuration being evaluated.
- **NullAway:** the project's own configuration, plus `JSpecifyMode=true JSpecifyExperimental=true`.
  Projects leave out `JSpecifyExperimental`, and with it JSpecify's JDK models, so their own
  NullAway setting is not a fair comparison. On context-propagation it reports 0 findings where
  the experimental setting reports 9.

## What makes a run trustworthy

- **Canaries.** Each run adds one class that returns a `@Nullable` parameter from a non-null
  method. One copy goes in a `@NullMarked` package, where EISOP must report it. The other goes in a
  new, unmarked package, where under `-Amode=jspecify` EISOP must not. If either check fails, the
  run fails. This catches a checker that silently never ran.
- **No javac errors.** The Checker Framework skips type-checking once javac has reported any
  error. So the init script removes `-Werror`, passes `-Awarns`, and demotes NullAway, which these
  projects configure as an error, to a warning. NullAway's findings therefore land in the same log.
- **Crashes fail the run, and invalidate the comparison.** A crash is reported as a javac error.
  It stops EISOP checking the rest of that file, and javac then stops analyzing later classes, so
  NullAway loses findings too. `comparison.md` is marked invalid when that happens.
- **Scoping anomalies.** Any EISOP diagnostic in a file outside `@NullMarked` scope is listed
  separately, because `-Amode=jspecify` should make that impossible.

## Running locally

```bash
# in an eisop/checker-framework checkout
./gradlew publishToMavenLocal -x javadoc -x allJavadoc
# here
./run-project.sh context-propagation
```

On macOS the JDK comes from `/usr/libexec/java_home -v <jdk>`; elsewhere set `JDK_HOME_25`.

## Status

`context-propagation` (EISOP 026312a, JDK 25) runs end to end and passes both canaries, but it is
**blocked by a crash, so there is no baseline**.

- **The crash.** `-AjspecifyUnrecognizedLocations`, which the mode turns on, crashes in
  `TreeUtils.getExplicitAnnotationTrees` on a method reference whose qualifier is a method call
  (`capture()::wrap`, `ContextExecutorService.java:77`). The run reports 22 EISOP findings and 6
  NullAway findings, both incomplete.
- **What the complete result looks like.** Before this repo settled on the mode alone, it ran the
  mode's options without `-AjspecifyUnrecognizedLocations`. That run did not crash, and it is the
  expected result once the crash is fixed:
  - EISOP 29, NullAway 9, at 16 locations: 9 reported by both, 7 by EISOP only, 0 by NullAway only.
    The location check itself reported nothing, so turning it back on should not add findings.
  - **Both tools report:** 7 overrides that give `<T>` a non-null bound where the JDK's is
    nullable, and 2 `Map.put(key, accessor.getValue())` calls. At those 9 locations EISOP reports
    21 findings, because one bad override bound produces up to 3 EISOP findings.
  - **EISOP's annotated JDK, which disagrees with JSpecify's JDK models:** 4 `Future<?>`
    overrides clash with EISOP's `Future<@Nullable ?>`, and `ContextRegistry.java:91-92` clash
    with its `ThreadLocal<@Nullable T>`.
  - **EISOP only, probably a real bug:** `ContextRegistry.java:108` passes a
    `V extends @Nullable Object` as the type argument of `ThreadLocalAccessor<V>`, whose `V` is
    non-null.
- **The scoping-anomaly counter proves nothing here.** Every one of the project's 13 main source
  files is in a `@NullMarked` package, so the counter cannot fire. Only the unmarked canary checks
  scoping on this project.

The other Gradle projects are `untried`, and CI runs them only when named explicitly. Their builds
may need per-project tasks or flags before their numbers mean anything. Maven projects
(`spring-grpc`, `guava`) need an injection path that does not exist yet.

`eisop/guava` is not a corpus member. It is EISOP's Checker Framework-annotated fork and has no
`@NullMarked` packages; upstream `google/guava` is the JSpecify one.

## Known caveats

- An explicit `-processor` turns off processor discovery, so the init script re-lists the
  processors it finds in the existing processor path's service files.
- The checker and its checker-qual go first on the processor path and classpath. Error Prone's
  dependencies carry an older `org.checkerframework` checker-qual that would otherwise shadow them.
- `CI` is unset for the build, because several projects hide Error Prone warnings on CI.
