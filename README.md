# North Standard

**Contract-bound evidence verification for physical GPU-service settlement.**

North Standard is a Monad Metropolis 2026 research/engineering project investigating a narrow question:

> Given incomplete, sampled, and potentially adversarial evidence, how reliably can a verifier distinguish compliant GPU service from breached service strongly enough to drive deterministic financial settlement?

The current repository is deliberately **not** a GPU marketplace. The verifier and its measurable behavior are the technical center.

## Current architecture

North Standard uses two verifier implementations with distinct roles:

- **C++20 core** — settlement-critical parsing, claim appraisal, hashing, and decision semantics;
- **Python reference** — simulator, research orchestration, experiment tooling, and executable semantic reference.

The JSON Schemas are the language-neutral protocol boundary. CI now sends Python-generated wire objects through the C++ parser and requires parity for:

```text
contract hash
+ evidence bundle root
+ settlement commitment hash
+ ACCEPT / REJECT / INCONCLUSIVE
+ reason codes
```

```text
Compute contract + evidence JSON
             |
             v
      canonical bytes
             |
      +------+------+
      |             |
   Python         C++20
 reference        core
      |             |
      +------v------+
       exact parity
             |
             v
 settlement commitment
             |
             v
      Monad (next step)
```

See [`docs/CANONICALIZATION.md`](docs/CANONICALIZATION.md) for the NSCJ-0.1 hashing profile.

## Implemented

- versioned compute-contract, evidence, verifier-result, and settlement-commitment schemas;
- deterministic UTF-8 canonical JSON in Python and C++20;
- cross-language SHA-256 parity;
- C++ JSON parsing into typed contract/evidence structures;
- preservation of unrecognized evidence payload fields;
- contract/session binding checks;
- runtime, availability, and performance claim appraisal;
- explicit `INCONCLUSIVE` behavior for ambiguous/missing evidence;
- replay and duplicate-evidence protection;
- compact `settlement-commitment/0.1` hash shared by Python and C++;
- four synthetic judge-facing scenarios;
- native C++ tests;
- Python unit tests;
- cross-language differential tests in CI.

Not implemented yet:

- Monad settlement contract;
- settlement authorization signature / verifier key management;
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

`INCONCLUSIVE` is first-class. Verifier failure or ambiguous evidence must not silently become provider success or provider fault.

## Build and test

### Python reference

Requires Python 3.11+.

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

### C++20 core

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

Canonicalize or hash arbitrary v0.1 JSON:

```bash
printf '{"b":2,"a":1.0}' | ./build/cpp/north-standard-cpp canonicalize-json
printf '{"b":2,"a":1.0}' | ./build/cpp/north-standard-cpp hash-json
```

Verify shared wire JSON:

```bash
./build/cpp/north-standard-cpp verify-json < wire.json
```

Expected high-level scenario decisions:

```text
healthy_service              -> ACCEPT
replayed_evidence            -> REJECT
constant_throttle            -> REJECT
ambiguous_network_failure    -> INCONCLUSIVE
```

## Repository layout

```text
CMakeLists.txt              top-level native build
cpp/                        C++20 parser/verifier/hash core + tests
schemas/                    JSON wire-format schemas
fixtures/                   shared cross-language parity vectors
src/north_standard/         Python reference verifier + simulator
tests/                      Python + cross-language differential tests
examples/                   executable vertical-slice examples
docs/                       architecture and protocol notes
contracts/                  reserved for Monad settlement milestone
experiments/                reserved for adversarial evaluation harness
app/                        reserved for the product console
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the verifier boundary.

## Research honesty

The simulator's current performance floor is **experiment-defined**, not a measured production SLA threshold. Synthetic evidence validates decision logic and adversarial experiment mechanics; it is not evidence of live H100 verification.

Future results will explicitly label evidence origin as synthetic, recorded accessible hardware, or live remote hardware.

## License

Apache License 2.0.
