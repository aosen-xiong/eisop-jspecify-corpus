# reactor-pool

- sha: `6d40ec6e904fa6048709eefeef6858d48063e735`
- eisop_version: `3.49.5-eisop2-SNAPSHOT`
- java_home: `/Library/Java/JavaVirtualMachines/jdk-25.jdk/Contents/Home`
- gradle_exit: `0`
- compile tasks the checker was injected into: 2
  - `:reactor-pool:compileJava: -processor org.checkerframework.checker.nullness.NullnessChecker -Amode=jspecify; NullAway: JSpecifyMode=true JSpecifyExperimental=true; javac: JDK 21 (21.0.7)`
  - `:reactor-pool-micrometer:compileJava: -processor org.checkerframework.checker.nullness.NullnessChecker -Amode=jspecify; NullAway: JSpecifyMode=true JSpecifyExperimental=true; javac: JDK 21 (21.0.7)`
- @NullMarked packages: 4; class-level marked/unmarked files: 1; NullAway suppression sites: 2
- EISOP diagnostics: 44 (0 jspecify.unrecognized.location.*)
- NullAway diagnostics: 1
- crash lines: 0; compiler errors not tied to a file: 0
- EISOP diagnostics in unmarked files (scoping anomalies): 0
- marked canary (expect EISOP reported): tools reporting it: eisop, nullaway
- unmarked canary (expect EISOP not reported): tools reporting it: none

| tool | key | count |
|---|---|---|
| eisop | `type.argument.type.incompatible` | 21 |
| eisop | `type.arguments.not.inferred` | 16 |
| eisop | `bound.type.incompatible` | 5 |
| eisop | `argument.type.incompatible` | 2 |
| nullaway | `NullAway` | 1 |
