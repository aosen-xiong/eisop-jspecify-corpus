# EISOP JSpecify-mode corpus

Runs the EISOP Nullness Checker's `-Amode=jspecify` over pinned revisions of real
JSpecify-annotated projects that already check themselves with NullAway, and records what EISOP
reports inside their `@NullMarked` scope.

The projects need no edits. An init script, `eisop-nullness.init.gradle`, adds the checker to their
compile tasks, the same idea as NullAway's `compile-other-projects` CI job. There are two
differences. NullAway's job only swaps a version and checks that the build passes. This one also
adds the processor, and it records each diagnostic so runs can be compared against a baseline.

## Layout

| file | purpose |
|---|---|
| `corpus.tsv` | the projects: repo, pinned SHA, build system, compile tasks, JDK, status |
| `eisop-nullness.init.gradle` | injects the checker; configured by `EISOP_VERSION`, `EISOP_ARGS`, `EISOP_TASKS` |
| `run-project.sh <name> [arm...]` | clones at the pinned SHA, adds canaries, runs each arm, summarizes |
| `summarize.py` | `build.log` → `diagnostics.tsv`, `counts.tsv`, `summary.md` |
| `diff.py <base> <new>` | compares two `diagnostics.tsv` by (tool, key, file, message), ignoring line shifts |
| `baselines/<project>/<arm>/` | stored `diagnostics.tsv` and `summary.md` that CI diffs against |

## Arms

| arm | options |
|---|---|
| `jspecify` | `-Amode=jspecify` |
| `jspecify-nolocations` | the mode's options except `-AjspecifyUnrecognizedLocations`, spelled out |
| `jspecify-bytecode` | `-Amode=jspecify -AuseConservativeDefaultsForUncheckedCode=bytecode` |

The second arm spells out its options because every option the mode adds is a presence flag with
no negative form. Once `-Amode=jspecify` is passed, none of them can be turned off.

## What makes a run trustworthy

- **Canaries.** Each run adds one class that returns a `@Nullable` parameter from a non-null
  method. One copy goes in a `@NullMarked` package, where EISOP must report it. The other goes in a
  new, unmarked package, where under `-AonlyAnnotatedFor` EISOP must not. If either check fails,
  the arm fails. This catches a checker that silently never ran.
- **No javac errors.** The Checker Framework skips type-checking once javac has reported any
  error. So the init script removes `-Werror`, passes `-Awarns`, and demotes NullAway, which these
  projects configure as an error, to a warning. NullAway's findings therefore land in the same log.
- **Crashes fail the arm.** A crash also stops checking of the rest of that file, so the counts
  would undercount.
- **Scoping anomalies.** Any EISOP diagnostic in a file outside `@NullMarked` scope is listed
  separately, because `-AonlyAnnotatedFor` should make that impossible.

## Running locally

```bash
# in an eisop/checker-framework checkout
./gradlew publishToMavenLocal -x javadoc -x allJavadoc
# here
./run-project.sh context-propagation
```

On macOS the JDK comes from `/usr/libexec/java_home -v <jdk>`; elsewhere set `JDK_HOME_25`.

## Status

`context-propagation` (EISOP 026312a, JDK 25) runs end to end, and all three arms pass both
canaries.

- **`jspecify`: blocked by a crash, so no baseline.** `-AjspecifyUnrecognizedLocations` crashes in
  `TreeUtils.getExplicitAnnotationTrees` on a method reference whose qualifier is a method call
  (`capture()::wrap`, `ContextExecutorService.java:77`). The crash ends checking of that file, so
  this arm reports 22 EISOP diagnostics where the uncrashed arm reports 29. The 7 missing ones are
  all in that file, below the crash site.
- **The location check itself never fired.** Across the whole project it reported zero
  `jspecify.unrecognized.location.*` diagnostics. Once the crash is fixed, `jspecify` and
  `jspecify-nolocations` are expected to match.
- **`jspecify-nolocations`: 29 EISOP diagnostics, 0 from NullAway.** 20 are `override.*` reports on
  `ExecutorService` / `ScheduledExecutorService` overrides. The rest are argument and type-argument
  reports around `ThreadLocal` and `Map.put`. They have not been triaged yet.
- **`jspecify-bytecode`: blocked by the same crash, so no baseline.** Compared with `jspecify`, it
  adds 2 diagnostics, both in `Slf4jThreadLocalAccessor`: a return and a `Map.put` argument,
  involving the unmarked SLF4J dependency.
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
