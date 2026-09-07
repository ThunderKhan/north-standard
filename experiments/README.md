# Verifier Experiments

This directory is the experimental control plane for North Standard's verifier research.

## Current milestone: synthetic smoke harness

The first harness is intentionally **not a benchmark result**. It exists to prove that the repository can:

1. generate seeded evidence without exposing ground truth to the verifier;
2. retain explicit `COMPLIANT` / `BREACH` labels only in the experiment harness;
3. run the same deterministic verifier used by the settlement path;
4. persist per-trial raw records;
5. calculate FAR, FRR, and INCONCLUSIVE rates with explicit denominators.

Current synthetic families:

| Case | Hidden ground truth | Purpose |
| --- | --- | --- |
| `healthy_variance` | COMPLIANT | healthy control with observation variance |
| `marginal_healthy` | COMPLIANT | measurement-noise stress near the experimental floor |
| `mild_throttle` | BREACH | near-boundary performance degradation |
| `severe_throttle` | BREACH | obvious performance degradation |
| `replayed_evidence` | BREACH | session-binding/replay attack |
| `buyer_network_failure` | COMPLIANT | ambiguous buyer/network fault; should abstain |
| `provider_outage` | BREACH | corroborated provider-side availability failure |
| `telemetry_gap` | COMPLIANT | required-evidence missingness / abstention |

Run locally:

```bash
python -m pip install -e .
python experiments/run_synthetic.py \
  --trials-per-scenario 25 \
  --base-seed 20260907
```

Outputs are written under `experiments/results/raw/synthetic-smoke/` and ignored by git.

## Metric definitions

```text
FAR = breach trials incorrectly ACCEPTed / all breach trials
FRR = compliant trials incorrectly REJECTed / all compliant trials
IR  = INCONCLUSIVE trials / all trials
```

The summary also reports IR conditioned on compliant and breach ground truth.

## Research honesty

Any numbers produced by this smoke harness are **synthetic pipeline diagnostics**. They are not final evidence that North Standard detects real provider cheating. Before numbers become research/pitch claims we still need, at minimum:

- a frozen held-out attack suite;
- meaningful baseline implementations;
- ablations;
- confidence intervals and exact sample counts;
- challenge-overhead measurements;
- recorded-real RTX 3050 traces;
- limitations and negative-result retention.
