# EISOP vs NullAway, by source location

- diagnostics: EISOP 44, NullAway 1
- locations: 44 both 0, eisop-only 43, nullaway-only 1

## Reported by EISOP only (43)

| location | EISOP keys | NullAway |
|---|---|---|
| `reactor/pool/AbstractPool.java:158` | `type.argument.type.incompatible` |  |
| `reactor/pool/AbstractPool.java:168` | `type.arguments.not.inferred` |  |
| `reactor/pool/AbstractPool.java:174` | `type.argument.type.incompatible` |  |
| `reactor/pool/AbstractPool.java:176` | `type.arguments.not.inferred` |  |
| `reactor/pool/AbstractPool.java:179` | `type.arguments.not.inferred` |  |
| `reactor/pool/AbstractPool.java:363` | `type.argument.type.incompatible` |  |
| `reactor/pool/AbstractPool.java:371` | `type.argument.type.incompatible` |  |
| `reactor/pool/Pool.java:180` | `type.argument.type.incompatible` |  |
| `reactor/pool/PoolBuilder.java:581` | `type.argument.type.incompatible` |  |
| `reactor/pool/PoolBuilder.java:594` | `type.argument.type.incompatible`, `type.arguments.not.inferred` |  |
| `reactor/pool/PooledRef.java:69` | `type.argument.type.incompatible` |  |
| `reactor/pool/PooledRef.java:83` | `type.argument.type.incompatible` |  |
| `reactor/pool/SimpleDequePool.java:178` | `type.argument.type.incompatible` |  |
| `reactor/pool/SimpleDequePool.java:179` | `type.arguments.not.inferred` |  |
| `reactor/pool/SimpleDequePool.java:436` | `argument.type.incompatible` |  |
| `reactor/pool/SimpleDequePool.java:444` | `argument.type.incompatible` |  |
| `reactor/pool/SimpleDequePool.java:466` | `type.arguments.not.inferred` |  |
| `reactor/pool/SimpleDequePool.java:489` | `type.argument.type.incompatible` |  |
| `reactor/pool/SimpleDequePool.java:490` | `type.arguments.not.inferred` |  |
| `reactor/pool/SimpleDequePool.java:534` | `bound.type.incompatible` |  |
| `reactor/pool/SimpleDequePool.java:674` | `type.argument.type.incompatible` |  |
| `reactor/pool/SimpleDequePool.java:675` | `type.arguments.not.inferred` |  |
| `reactor/pool/SimpleDequePool.java:690` | `type.argument.type.incompatible` |  |
| `reactor/pool/SimpleDequePool.java:691` | `type.arguments.not.inferred` |  |
| `reactor/pool/SimpleDequePool.java:751` | `type.argument.type.incompatible` |  |
| `reactor/pool/SimpleDequePool.java:753` | `bound.type.incompatible` |  |
| `reactor/pool/SimpleDequePool.java:765` | `bound.type.incompatible` |  |
| `reactor/pool/SimpleDequePool.java:767` | `bound.type.incompatible` |  |
| `reactor/pool/SimpleDequePool.java:874` | `type.argument.type.incompatible` |  |
| `reactor/pool/SimpleDequePool.java:898` | `bound.type.incompatible` |  |
| `reactor/pool/decorators/GracefulShutdownInstrumentedPool.java:59` | `type.argument.type.incompatible` |  |
| `reactor/pool/decorators/GracefulShutdownInstrumentedPool.java:69` | `type.arguments.not.inferred` |  |
| `reactor/pool/decorators/GracefulShutdownInstrumentedPool.java:174` | `type.argument.type.incompatible` |  |
| `reactor/pool/decorators/GracefulShutdownInstrumentedPool.java:235` | `type.argument.type.incompatible` |  |
| `reactor/pool/decorators/GracefulShutdownInstrumentedPool.java:242` | `type.arguments.not.inferred` |  |
| `reactor/pool/decorators/GracefulShutdownInstrumentedPool.java:261` | `type.argument.type.incompatible` |  |
| `reactor/pool/decorators/GracefulShutdownInstrumentedPool.java:289` | `type.argument.type.incompatible` |  |
| `reactor/pool/decorators/GracefulShutdownInstrumentedPool.java:291` | `type.arguments.not.inferred` |  |
| `reactor/pool/decorators/GracefulShutdownInstrumentedPool.java:293` | `type.arguments.not.inferred` |  |
| `reactor/pool/decorators/GracefulShutdownInstrumentedPool.java:309` | `type.argument.type.incompatible` |  |
| `reactor/pool/decorators/GracefulShutdownInstrumentedPool.java:311` | `type.arguments.not.inferred` |  |
| `reactor/pool/decorators/GracefulShutdownInstrumentedPool.java:313` | `type.arguments.not.inferred` |  |
| `reactor/pool/introspection/SamplingAllocationStrategy.java:56` | `type.arguments.not.inferred` |  |

## Reported by NullAway only (1)

| location | EISOP keys | NullAway |
|---|---|---|
| `reactor/pool/SimpleDequePool.java:208` |  | dereferenced expression 'ref' is @Nullable |
