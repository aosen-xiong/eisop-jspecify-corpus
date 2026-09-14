# context-propagation / nullaway-experimental

- sha: `6a9d15dcd0b6b491ad6d4f6ef809a722056029e0`
- args: `-AonlyAnnotatedFor -AjspecifyNullMarkedAlias=true -AassumeInitialized -AassumeKeyFor`
- eisop_version: `3.49.5-eisop2-SNAPSHOT`
- java_home: `/Library/Java/JavaVirtualMachines/jdk-25.jdk/Contents/Home`
- gradle_exit: `0`
- compile tasks the checker was injected into: 1
- @NullMarked packages: 2; class-level marked/unmarked files: 2; NullAway suppression sites: 0
- EISOP diagnostics: 29 (0 jspecify.unrecognized.location.*)
- NullAway diagnostics: 9
- crash lines: 0; compiler errors not tied to a file: 0
- EISOP diagnostics in unmarked files (scoping anomalies): 0
- marked canary (expect EISOP reported): tools reporting it: eisop, nullaway
- unmarked canary (expect EISOP not reported): tools reporting it: none

| tool | key | count |
|---|---|---|
| eisop | `override.return.invalid` | 9 |
| eisop | `override.param.invalid` | 7 |
| eisop | `override.typaram.invalid` | 7 |
| eisop | `argument.type.incompatible` | 3 |
| eisop | `type.argument.type.incompatible` | 2 |
| eisop | `methodref.param.invalid` | 1 |
| errorprone | `NotJavadoc` | 2 |
| errorprone | `TypeParameterUnusedInFormals` | 1 |
| nullaway | `NullAway` | 9 |
