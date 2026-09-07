# North Standard — v0.1 Architecture

North Standard is an experimental verifier for contract-bound physical GPU service. The market is an application shell; the verifier and its measurable behavior are the technical center.

## Separation of concerns

```text
Compute Contract
      |
      v
Contract-bound session
      |
      +-- session binding
      +-- runtime evidence
      +-- telemetry
      +-- randomized challenge evidence
      +-- independent probes
      |
      v
Evidence Bundle
      |
      v
C++ verifier core <---- differential parity ---- Python reference
      |
      +-- claim results
      |     session.binding
      |     service.runtime
      |     service.availability
      |     service.performance
      |
      v
ACCEPT | REJECT | INCONCLUSIVE
      |
      v
Signed/result commitment (next milestone)
      |
      v
Monad settlement policy (next milestone)
```

The verifier appraises evidence. It does **not** decide how much money moves. Financial consequences belong in a separate settlement policy.

## Why two implementations?

The Python verifier remains the fast-moving research/reference implementation. The C++20 core is the candidate settlement-critical implementation because it gives tighter control over types, native execution, future GPU/CUDA integration, and high-volume experiment replay.

Neither implementation is allowed to silently become the source of different semantics. Shared scenarios are executed through both in CI. Decision and reason-code disagreement is a test failure.

This is not yet full wire-level equivalence. The current cross-language invariant covers typed verifier semantics. Canonical JSON parsing/serialization and SHA-256 commitment parity are intentionally deferred to the next boundary-hardening milestone.

## Current claims

The v0.1 executable slice requires four claims:

- `session.binding`
- `service.runtime`
- `service.availability`
- `service.performance`

Hardware identity is intentionally deferred until a real hardware-attestation adapter exists. Location, exclusivity, and network SLA claims are not implied.

## C++ core boundary

The C++ core currently owns:

- typed contract/evidence structures;
- binding/replay appraisal;
- runtime appraisal;
- availability appraisal;
- performance appraisal;
- fatal duplicate detection;
- overall `ACCEPT | REJECT | INCONCLUSIVE` semantics;
- native scenario execution.

It intentionally does **not** yet own:

- JSON Schema validation;
- canonical JSON serialization;
- evidence-bundle hashing;
- verifier-result signing;
- settlement transaction submission;
- GPU/CUDA challenge execution.

Those boundaries should be added deliberately rather than hidden behind fake completeness.

## Conservative decision policy

```text
mandatory CONTRADICTING -> REJECT
fatal INVALID            -> REJECT
mandatory UNKNOWN        -> INCONCLUSIVE
all mandatory AFFIRMING  -> ACCEPT
otherwise                -> INCONCLUSIVE
```

Missing evidence never silently becomes success.

## Shared v0.1 scenarios

| Scenario | Intended output | Purpose |
|---|---|---|
| `healthy_service` | `ACCEPT` | happy path |
| `replayed_evidence` | `REJECT` | contract/session binding |
| `constant_throttle` | `REJECT` | performance breach path |
| `ambiguous_network_failure` | `INCONCLUSIVE` | preserve uncertainty |

## Next architectural milestone

Before Solidity consumes verifier output, harden the language boundary:

1. canonical schema-backed verifier input in C++;
2. C++/Python canonical commitment parity;
3. settlement authorization object;
4. verifier signature/key policy;
5. Monad smart contract consuming only the compact authorized result.

Then:

```text
ACCEPT       -> provider payment path
REJECT       -> buyer refund / configured penalty path
INCONCLUSIVE -> HELD path
```

Raw telemetry must never directly move funds.
