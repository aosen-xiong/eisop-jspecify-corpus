# EISOP JSpecify-mode corpus

Runs the EISOP Nullness Checker's `-Amode=jspecify` over pinned revisions of real
JSpecify-annotated projects that already check themselves with NullAway. It records what EISOP
reports inside their `@NullMarked` scope, and compares it with NullAway on the same code.

The projects need no edits. An init script, `eisop-nullness.init.gradle`, adds the checker to their
compile tasks, the same idea as NullAway's `compile-other-projects` CI job. There are two
differences. NullAway's job only swaps a version and checks that the build passes. This one also
adds the processor, and it records each diagnostic so runs can be compared against a baseline.

Current results per project are in [STATUS.md](STATUS.md).

## Layout

| file | purpose |
|---|---|
| `corpus.tsv` | the projects: repo, pinned SHA, build system, compile tasks, JDK, status |
| `eisop-nullness.init.gradle` | injects the checker and sets its options and NullAway's; configured by `EISOP_VERSION`, `EISOP_TASKS` and `EISOP_COMPILE_JDK` |
| `run-project.sh <name>` | clones at the pinned SHA, adds canaries, builds, summarizes, compares |
| `summarize.py` | `build.log` → `diagnostics.tsv`, `counts.tsv`, `summary.md` |
| `compare.py <diagnostics.tsv>` | pairs EISOP and NullAway findings by (file, line) into both / EISOP-only / NullAway-only → `comparison.md` |
| `triage.py <src> <result-dir>` | assigns every EISOP and NullAway finding a cause category → `triage.tsv`; see [TRIAGE.md](TRIAGE.md) |
| `diff.py <base> <new>` | compares two `diagnostics.tsv` by (tool, key, file, message), ignoring line shifts |
| `baselines/<project>/` | stored `diagnostics.tsv` that CI diffs against |
| `STATUS.md` | current results and open problems per project |

## Run setting

Each project is built once, with both tools in the same compile.

- **EISOP:** `-Amode=jspecify` and nothing else. It is the configuration being evaluated.
- **NullAway:** the project's own configuration, plus `JSpecifyMode=true JSpecifyExperimental=true`.
  Projects leave out `JSpecifyExperimental`, and with it JSpecify's JDK models, so their own
  NullAway setting is not a fair comparison. On context-propagation it reports 0 findings where
  the experimental setting reports 9. NullAway itself is pinned to 0.14.1 in every project, as
  NullAway's own compile-other-projects job swaps in one version: projects pin their own, and a
  version before 0.14.0 silently ignores `JSpecifyExperimental`. `summary.md` names the NullAway
  jar each compile task actually used.
- **Compiler:** the checked compile tasks use the manifest's JDK (the `jdk` column), whatever
  compiler or toolchain the project configures, so every project is checked by the same javac. The
  project's `--release` is kept; a project releasing for a newer Java than its `jdk` column fails
  to build, and needs that column raised. If the project's build has already locked a task's
  compiler (reading `javaCompiler` in Gradle locks it), that task keeps the project's compiler and
  the build log says so. Before JDK 22, javac does not read
  type-use annotations such as `@Nullable` on a type argument from dependency class files, so on
  an older toolchain both tools would silently see a `@NullMarked` dependency's generic types
  unannotated. `summary.md` records the JDK each compile task actually used.

## What makes a run trustworthy

- **Canaries.** Each run adds a class that returns a `@Nullable` parameter from a non-null method,
  as a pair in every source root that has a `@NullMarked` package. One copy goes in a `@NullMarked`
  package, where EISOP must report it. The other goes in a new package and is annotated
  `@NullUnmarked`, where under `-Amode=jspecify` EISOP must not. A root is judged only if its
  module's compile task ran: in a multi-module build, one failing module stops every module that
  depends on it from compiling. The run fails if EISOP misses a compiled root's marked canary,
  reports any unmarked canary, or no root compiled at all. This catches a checker that silently
  never ran. The second copy is explicitly `@NullUnmarked` because some projects run Error Prone's
  `RequireExplicitNullMarking` as an error, and that error would stop EISOP in the whole module.
- **No javac errors.** The Checker Framework skips type-checking once javac has reported any
  error. So the init script removes `-Werror`, passes `-Awarns`, and demotes NullAway, which these
  projects configure as an error, to a warning. NullAway's findings therefore land in the same log.
- **An EISOP crash fails the run and invalidates the comparison.** EISOP reports a crash as a
  javac error, and it harms both tools' results in different ways:
  - EISOP skips the rest of the file it crashed in, but keeps checking other files.
  - Error Prone, and with it NullAway, skips every file compiled after the crash. Which files those
    are depends on compile order, which differs between machines, so a crashed run's NullAway
    results can differ between a local run and CI.

  `comparison.md` is marked invalid when that happens.
- **Recovered internal failures do not fail the run.** A `*.crashed` warning key, such as
  `type.argument.inference.crashed`, means EISOP caught an internal failure and kept checking. It
  is counted separately in `summary.md`, unlike a crash, which stops checking.
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

## Known caveats

- An explicit `-processor` turns off processor discovery, so the init script re-lists the
  processors it finds in the existing processor path's service files.
- The checker and its checker-qual go first on the processor path and classpath. Error Prone's
  dependencies carry an older `org.checkerframework` checker-qual that would otherwise shadow them.
- `CI` is unset for the build, because several projects hide Error Prone warnings on CI.
- The configuration cache is off, because the init script's task actions hold Gradle objects it
  cannot store. Isolated Projects, which requires it and which junit-framework enables in
  `gradle.properties`, is turned off with `-Dorg.gradle.isolated-projects=false`.
- Included builds and `buildSrc` are left untouched: they are the project's build logic, not code
  under evaluation.
- `mavenLocal()` is added to the settings-level repositories, and to a project's own repositories
  only if it already declares some or settings declares none. A project that declares any
  repository no longer sees the settings-level ones, so adding it unconditionally hid every real
  repository from projects that rely on settings.
- When the checked task compiles a named module (a `module-info.java`), the checker's qualifiers are
  added with `--add-modules org.checkerframework.checker.qual`; a module does not read the
  classpath.
- NullAway is demoted to a warning both in Error Prone's check map and through the
  `net.ltgt.nullaway` plugin's own extension, which would otherwise re-apply the project's
  `nullaway { error() }` afterwards. `summary.md` logs the NullAway arguments Error Prone actually
  receives.
