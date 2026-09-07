# North Standard — v0.1 Architecture

North Standard is currently an experimental verifier for contract-bound physical GPU service. The market is an application shell; the verifier and its measurable behavior are the technical center.

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
Verifier
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

## Current claims

The v0.1 executable slice requires four claims:

- `session.binding`
- `service.runtime`
- `service.availability`
- `service.performance`

Hardware identity is intentionally deferred until a real hardware-attestation adapter exists. Location, exclusivity, and network SLA claims are not implied.

## Evidence provenance

The code supports the evidence classes needed for the first slice and leaves room for later adapters:

- `SESSION_BINDING`
- `RUNTIME_CHECK`
- `TELEMETRY`
- `CHALLENGE`
- `EXTERNAL_PROBE`
- `HARDWARE_ATTESTATION` (adapter not implemented)
- `ADMIN_EVENT`

A signed record is not automatically sufficient for every claim. The verifier evaluates evidence by type and context.

## Conservative decision policy

```text
mandatory CONTRADICTING -> REJECT
fatal INVALID            -> REJECT
mandatory UNKNOWN        -> INCONCLUSIVE
all mandatory AFFIRMING  -> ACCEPT
otherwise                -> INCONCLUSIVE
```

Missing evidence never silently becomes success.

## Research-mode thresholds

The Step-1 simulator uses an explicitly experiment-defined normalized performance floor so the decision path can be exercised. It is not a calibrated production threshold and must not be presented as an H100 SLA recommendation.

## Step-1 scenarios

| Scenario | Intended output | Purpose |
|---|---|---|
| `healthy_service` | `ACCEPT` | happy path |
| `replayed_evidence` | `REJECT` | contract/session binding |
| `constant_throttle` | `REJECT` | performance breach path |
| `ambiguous_network_failure` | `INCONCLUSIVE` | preserve uncertainty |

## Next architectural milestone

The next vertical slice adds a settlement authorization object and a Monad smart contract that consumes only the versioned verifier result commitment:

```text
ACCEPT       -> provider payment path
REJECT       -> buyer refund / configured penalty path
INCONCLUSIVE -> HELD path
```

Raw telemetry must never directly move funds.
