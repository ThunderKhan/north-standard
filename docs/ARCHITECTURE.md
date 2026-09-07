# North Standard — v0.1 Architecture

North Standard is an experimental verification-and-settlement system for contract-bound physical GPU service. The market is an application shell; the measurable verifier is the technical center.

## System boundary

```text
Compute Contract
      |
      v
Contract-bound service session
      |
      +-- session binding evidence
      +-- runtime evidence
      +-- telemetry
      +-- challenge evidence
      +-- external probes
      |
      v
Evidence Bundle
      |
      +-----------------------------+
      |                             |
      v                             v
C++20 verifier core <---- parity ---- Python reference / experiment control plane
      |                             |
      | canonical JSON + SHA-256    | synthetic/recorded/live provenance
      | claim appraisal             | ground-truth labels stay outside verifier
      | decision semantics          | baselines / ablations / metrics
      +-------------+---------------+
                    |
                    v
          settlement-commitment/0.1
                    |
                    v
          EIP-712 authorization data
                    |
             external signer
                    |
                    v
          SettlementAuthorization
                    |
                    v
       NorthStandardSettlement.sol
                    |
       +------------+-------------+
       |            |             |
     ACCEPT       REJECT     INCONCLUSIVE
       |            |             |
 provider paid   refund +         HELD
                 configured       funds remain
                 demo penalty     locked
```

Raw telemetry never directly moves funds. The verifier appraises evidence; settlement policy maps an authorized verifier result to financial state.

## C++20 verifier core

The C++ core currently owns settlement-critical deterministic mechanics:

- schema-aware typed contract/evidence parsing for the v0.1 wire boundary;
- canonical JSON representation;
- SHA-256 contract/evidence/settlement commitments;
- preservation of uninterpreted but commitment-relevant payload fields;
- binding/replay appraisal;
- runtime appraisal;
- availability appraisal;
- performance appraisal;
- duplicate/fatal evidence validation;
- `ACCEPT | REJECT | INCONCLUSIVE` semantics.

Python contains an independent executable reference. CI sends shared wire objects through both implementations and fails on mismatch in contract hash, evidence root, settlement commitment, decision, or reason codes.

## Settlement-critical commitment

The full verifier result may contain implementation/audit metadata. Financial authorization commits to a smaller language-neutral semantic payload:

```text
settlement-commitment/0.1
  contract_id
  session_id
  verifier_policy_id
  evidence_bundle_root
  claims { state, reason_codes }
  overall { decision, reason_codes }
```

This permits Python and C++ to retain different implementation metadata while requiring exact agreement about the financial statement.

## Signing boundary

The verifier does not own private keys. Python builds an unsigned EIP-712 `SettlementAuthorization` containing:

- agreement ID;
- canonical contract hash;
- settlement commitment;
- evidence bundle root;
- verifier-policy hash;
- settlement-policy hash;
- verifier-set ID;
- decision;
- issuance/expiry times;
- nonce.

A wallet, HSM, or secret-managed signer signs the typed data. The Solidity contract recovers and validates the authorized verifier address.

## Solidity settlement

`NorthStandardSettlement.sol` implements a native-token demonstration state machine:

```text
buyer escrow + provider collateral
              |
              v
          ACTIVE
              |
      authorized result
      /       |        \
 ACCEPT     REJECT   INCONCLUSIVE
   |           |          |
SETTLED     SETTLED      HELD
                          |
                 mutual resolution
                    or timeout
                          |
                       SETTLED
```

Important invariants:

- one agreement consumes at most one verifier result;
- result/policy/contract/verifier-set hashes must match the agreement;
- stale or unauthorized signatures cannot settle;
- verifier outage moves to `HELD`, not automatic provider rejection;
- `INCONCLUSIVE` does not silently become either party's victory;
- settlement credits pull-payment balances before withdrawal;
- raw evidence has no onchain path that directly changes financial state.

## Evaluation architecture

Ground truth is deliberately separated from verifier input.

```text
hidden experiment label
(COMPLIANT / BREACH)
        |
        +---- experiment harness only
        |
service/evidence generator
        |
        v
same verifier used by settlement
        |
        v
ACCEPT / REJECT / INCONCLUSIVE
        |
        v
compare with hidden label
        |
        +-- FAR
        +-- FRR
        +-- INCONCLUSIVE rate
        +-- conditioned abstention
```

Current research tooling includes:

- seeded synthetic trials;
- evidence-subset baselines;
- verifier ablations;
- challenge-aware cheating;
- predictable vs hidden challenge schedules;
- disjoint calibration/held-out seeds;
- Wilson confidence intervals;
- challenge-parameter sensitivity sweeps.

These facilities are reproducibility infrastructure. Synthetic results remain explicitly non-publication-ready.

## Conservative verifier policy

```text
mandatory CONTRADICTING -> REJECT
fatal INVALID            -> REJECT
mandatory UNKNOWN        -> INCONCLUSIVE
all mandatory AFFIRMING  -> ACCEPT
otherwise                -> INCONCLUSIVE
```

Missing evidence never silently becomes success.

## Current v0.1 claims

- `session.binding`
- `service.runtime`
- `service.availability`
- `service.performance`

Hardware identity remains deferred until a real hardware-attestation adapter exists. Location and exclusivity are not implied.

## Current execution modes

- **S — SYNTHETIC:** generated evidence for deterministic adversarial experiments;
- **R — RECORDED_REAL:** planned accessible-hardware traces, beginning with RTX 3050;
- **L — LIVE_REAL:** optional future remote-provider evidence.

Mode S establishes experiment mechanics and catches protocol/decision bugs. It must not be described as live GPU verification.

## Next architectural milestones

1. record real challenge/telemetry traces on accessible RTX 3050 hardware;
2. add the optional C++/CUDA challenge runner and measure runtime overhead;
3. broaden provider attacks (burst throttling, contention, conflicting telemetry/probes);
4. run frozen held-out baseline/ablation evaluation with retained raw outputs;
5. broadcast and independently verify the settlement contract on Monad Testnet once a dedicated funded testnet signer is configured;
6. add real hardware-attestation adapters when access permits;
7. build the product console only after the evidence/verifier/settlement path remains stable.
