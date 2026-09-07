# North Standard Settlement — Step 2

This contract is the deterministic financial consumer of North Standard verifier results.
It intentionally does **not** parse telemetry or evaluate GPU service itself.

## Boundary

```text
physical-service evidence
        ↓
C++ verifier
        ↓
settlement-commitment/0.1
        ↓
EIP-712 SettlementAuthorization
        ↓
NorthStandardSettlement.sol
        ↓
ACCEPT       → provider paid + collateral returned
REJECT       → buyer refunded + configured demo penalty
INCONCLUSIVE → HELD, no funds move
```

Raw telemetry cannot directly call a financial transition.

## Admission checks

A submitted authorization must bind to the exact agreement and match:

- `contractHash`
- `verifierPolicyHash`
- `settlementPolicyHash`
- `verifierSetId`
- non-zero `settlementCommitment`
- non-zero `evidenceBundleRoot`
- an authorized verifier signer
- the agreement's result window
- an unused verifier nonce

Each agreement consumes at most one verifier result in v0.1.

## EIP-712 authorization

Domain:

```text
name:    North Standard Settlement
version: 0.1
chainId: current chain
verifyingContract: deployed contract address
```

Type:

```text
SettlementAuthorization(
  bytes32 agreementId,
  bytes32 contractHash,
  bytes32 settlementCommitment,
  bytes32 evidenceBundleRoot,
  bytes32 verifierPolicyHash,
  bytes32 settlementPolicyHash,
  bytes32 verifierSetId,
  uint8 decision,
  uint64 issuedAt,
  uint64 validUntil,
  uint256 nonce
)
```

The C++ verifier's NSCJ/SHA-256 `settlement_hash` is carried as `settlementCommitment`.
The EIP-712 signature authorizes that commitment for one onchain agreement and one decision.

## Settlement policy

### ACCEPT

```text
buyer escrow + provider collateral → provider claimable balance
state → SETTLED
```

### REJECT

```text
buyer escrow → buyer
configured fraction of provider collateral → buyer
remaining provider collateral → provider
state → SETTLED
```

`rejectPenaltyBps` is a configurable demo/research parameter. It is not a claim about a production-optimal collateral penalty.

### INCONCLUSIVE

```text
escrow remains locked
collateral remains locked
state → HELD
```

This preserves the project's rule that ambiguity must not silently become provider success or provider fault.

## Verifier outage

If no verifier authorization arrives before `verifierDeadline`, anyone may call:

```solidity
enterHeldOnVerifierTimeout(agreementId)
```

The agreement moves to `HELD`; the provider is not automatically rejected or slashed.

## HELD exits

Two v0.1 paths are implemented:

1. **Mutual resolution** — buyer and provider sign the same EIP-712 allocation.
2. **Timeout neutral unwind** — after `holdTimeout`, buyer escrow returns to the buyer and provider collateral returns to the provider.

The timeout fallback is deliberately neutral rather than an automated liability judgment.

## Pull payments

Settlement credits `claimable[address]` balances. Parties withdraw separately with `withdraw()`.
No provider/buyer callback occurs inside the settlement transition itself.

## Local tests

```bash
forge test -vvv
```

The test suite covers:

- ACCEPT
- REJECT
- INCONCLUSIVE
- unauthorized verifier
- policy mismatch
- expired authorization
- replayed result
- verifier timeout → HELD
- HELD timeout unwind
- mutual resolution
- withdrawal

## Monad Testnet deployment

As of September 2026, official Monad developer sources identify Testnet chain ID `10143` and the native token as `MON`. Keep the RPC in an environment variable because public endpoints can change.

```bash
cp .env.example .env
# set DEPLOYER_PRIVATE_KEY to a dedicated funded TESTNET key only
source .env

forge script contracts/script/DeployNorthStandardSettlement.s.sol:DeployNorthStandardSettlement \
  --rpc-url "$MONAD_TESTNET_RPC_URL" \
  --broadcast
```

Do not commit private keys.

A real testnet deployment/transaction is intentionally not represented as completed until a funded testnet signing key is available and the transaction can be independently confirmed onchain.
