# North Standard

**Contract-bound evidence verification for physical GPU-service settlement.**

North Standard is a Monad Metropolis 2026 research/engineering project investigating a narrow question:

> Given incomplete, sampled, and potentially adversarial evidence, how reliably can a verifier distinguish compliant GPU service from breached service strongly enough to drive deterministic financial settlement?

The repository is deliberately **not** a GPU marketplace. The verifier and its measurable behavior are the technical center; Monad is the deterministic financial consumer of an authorized verifier result.

## Current architecture

```text
physical GPU-service evidence
          |
          v
 C++20 verifier core <----> Python research reference
          |                    (cross-language parity)
          v
 settlement-commitment/0.1
          |
          v
 unsigned EIP-712 signing package
          |
   external wallet / HSM / signer
          |
          v
 SettlementAuthorization signature
          |
          v
 NorthStandardSettlement.sol
          |
    +-----+------+----------------+
    |            |                |
  ACCEPT       REJECT       INCONCLUSIVE
    |            |                |
 provider      refund +           HELD
  paid       demo penalty       no funds move
```

Private keys are intentionally **not** handled by the verifier core. The repository builds the exact EIP-712 typed data; signing belongs to an external wallet, HSM, or secret-managed service.

## Implemented

### Verification boundary

- versioned compute-contract, evidence, verifier-result, settlement-commitment, and settlement-authorization schemas;
- deterministic UTF-8 canonical JSON in Python and C++20;
- cross-language SHA-256 parity;
- C++ JSON parsing into typed contract/evidence structures;
- preservation of unrecognized evidence payload fields;
- contract/session binding, replay protection, runtime, availability, and performance appraisal;
- explicit `ACCEPT`, `REJECT`, and `INCONCLUSIVE` semantics;
- compact `settlement-commitment/0.1` shared by Python and C++;
- differential CI for contract hash, evidence root, settlement hash, decisions, and reason codes.

### Settlement boundary

- EIP-712 `SettlementAuthorization` admission format;
- signer-facing Python package that binds the authorization to the exact C++/Python hashes;
- `NorthStandardSettlement.sol` escrow + provider-collateral state machine;
- authorized secp256k1 verifier signer recovery with low-s enforcement;
- authorization validity windows and nonce/replay protection;
- `ACCEPT` → provider payment path;
- `REJECT` → buyer refund + configurable research/demo collateral penalty;
- `INCONCLUSIVE` → `HELD` with no funds moved;
- verifier timeout → `HELD`, never automatic provider fault;
- mutually signed HELD resolution;
- neutral timeout unwind;
- pull-payment withdrawals;
- Foundry test suite in CI;
- guarded, manually triggered Monad Testnet deployment workflow.

Not implemented yet:

- a real Monad Testnet deployment transaction (requires a funded dedicated testnet key);
- production verifier key management/HSM integration;
- NVIDIA/H100 attestation adapter;
- C++/CUDA challenge runner;
- recorded-real GPU traces;
- adversarial experiment sweeps and FAR/FRR/IR measurements;
- production-calibrated thresholds;
- frontend/market shell.

## Decisions

Each mandatory claim returns one of:

```text
AFFIRMING
CONTRADICTING
UNKNOWN
NOT_EVALUATED
INVALID
```

The overall verifier returns:

```text
ACCEPT
REJECT
INCONCLUSIVE
```

The conservative v0.1 rule is:

```text
any mandatory contradiction -> REJECT
fatal invalid evidence       -> REJECT
any mandatory unknown        -> INCONCLUSIVE
all mandatory affirming      -> ACCEPT
```

`INCONCLUSIVE` is first-class. Ambiguous evidence or verifier outage must not silently become provider success or provider fault.

## Build and test

### Python reference

Requires Python 3.11+.

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

Generate an unsigned EIP-712 signing package:

```bash
python examples/build_authorization.py
```

### C++20 verifier

Requires CMake 3.20+ and a C++20 compiler.

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

Run a native scenario:

```bash
./build/cpp/north-standard-cpp simulate healthy_service
./build/cpp/north-standard-cpp simulate replayed_evidence
./build/cpp/north-standard-cpp simulate constant_throttle
./build/cpp/north-standard-cpp simulate ambiguous_network_failure
```

Verify shared wire JSON:

```bash
./build/cpp/north-standard-cpp verify-json < wire.json
```

### Solidity settlement

Requires Foundry.

```bash
forge test -vvv
```

See [`docs/SETTLEMENT_CONTRACT.md`](docs/SETTLEMENT_CONTRACT.md) for the admission and settlement policy.

## Monad Testnet deployment

A manual workflow lives at `.github/workflows/deploy-monad-testnet.yml`. It checks the RPC's chain ID is `10143` before broadcasting.

Configure the protected `monad-testnet` GitHub environment with:

```text
MONAD_TESTNET_RPC_URL
MONAD_TESTNET_DEPLOYER_PRIVATE_KEY
```

Use only a dedicated funded **testnet** key. Never commit or paste the key into source, logs, issues, or chat.

No deployment is claimed until the transaction and deployed contract can be independently confirmed onchain.

## Repository layout

```text
CMakeLists.txt              top-level native build
cpp/                        C++20 parser/verifier/hash core + tests
contracts/                  Solidity settlement, Foundry tests, deploy script
schemas/                    JSON wire-format schemas
fixtures/                   shared cross-language parity vectors
src/north_standard/         Python reference + authorization builder
tests/                      Python + cross-language differential tests
examples/                   executable examples
.github/workflows/          CI + guarded Monad Testnet deployment
docs/                       architecture and protocol notes
experiments/                adversarial evaluation workspace
app/                        reserved for the product console
```

## Research honesty

The simulator's current performance floor is **experiment-defined**, not a measured production SLA threshold. Synthetic evidence validates decision logic and adversarial experiment mechanics; it is not evidence of live H100 verification.

Likewise, `rejectPenaltyBps` is a configurable demonstration/research settlement parameter, not a claim about economically optimal production collateralization.

Future results will explicitly label evidence origin as synthetic, recorded accessible hardware, or live remote hardware.

## License

Apache License 2.0.
