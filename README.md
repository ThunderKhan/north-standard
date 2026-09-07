# North Standard

**Contract-bound evidence verification for physical GPU-service settlement.**

North Standard is a Monad Metropolis 2026 research/engineering project investigating a narrow question:

> Given incomplete, sampled, and potentially adversarial evidence, how reliably can a verifier distinguish compliant GPU service from breached service strongly enough to drive deterministic financial settlement?

The current repository is deliberately **not** a GPU marketplace. The first milestone is the verification boundary itself.

## Current v0.1 slice

```text
Compute contract
      -> contract-bound evidence
      -> deterministic verifier
      -> ACCEPT | REJECT | INCONCLUSIVE
```

Implemented in Step 1:

- versioned compute-contract, evidence, and verifier-result schemas;
- deterministic canonical serialization + SHA-256 commitments;
- contract/session binding checks;
- runtime, availability, and performance claim appraisal;
- explicit `INCONCLUSIVE` behavior for ambiguous/missing evidence;
- synthetic simulator with four judge-facing scenarios;
- replay/duplicate protection in the executable verifier path;
- dependency-free unit tests.

Not implemented yet:

- Monad settlement contract;
- result signing / verifier key management;
- NVIDIA/H100 attestation adapter;
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

## Run locally

Requires Python 3.11+ and no runtime dependencies.

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

Run a single scenario:

```bash
north-standard simulate healthy_service
north-standard simulate replayed_evidence
north-standard simulate constant_throttle
north-standard simulate ambiguous_network_failure
```

Or all four:

```bash
python examples/run_vertical_slice.py
```

Expected high-level decisions:

```text
healthy_service              -> ACCEPT
replayed_evidence            -> REJECT
constant_throttle            -> REJECT
ambiguous_network_failure    -> INCONCLUSIVE
```

## Repository layout

```text
schemas/                  JSON wire-format schemas
src/north_standard/       verifier + simulator implementation
tests/                    deterministic unit tests
examples/                 executable vertical-slice examples
docs/                     architecture and research-facing docs
contracts/                reserved for Monad settlement milestone
experiments/              reserved for adversarial evaluation harness
app/                      reserved for the product console
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the current design boundary.

## Research honesty

The simulator's current performance floor is **experiment-defined**, not a measured production SLA threshold. Synthetic evidence validates decision logic and adversarial experiment mechanics; it is not evidence of live H100 verification.

Future results will explicitly label evidence origin as synthetic, recorded accessible hardware, or live remote hardware.

## License

Apache License 2.0.
