# Verifier Experiments

This directory is the experimental control plane for North Standard's verifier research.

## Current milestone: reproducible synthetic evaluation plumbing

The current harnesses are intentionally **not benchmark results**. They now support:

1. seeded evidence with hidden ground truth outside the verifier;
2. FAR, FRR, and INCONCLUSIVE rates with explicit denominators;
3. evidence-subset baselines and verifier ablations;
4. challenge-aware cheating under predictable versus hidden schedules;
5. disjoint calibration/held-out seed namespaces;
6. 95% Wilson intervals so zero observed errors are never presented as zero uncertainty.

## General synthetic matrix

Current families:

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

```bash
python experiments/run_synthetic.py --trials-per-scenario 25 --base-seed 20260907
python experiments/compare_evaluators.py --trials-per-scenario 25 --base-seed 20260907
```

## Held-out protocol

Calibration and held-out runs use separate deterministic seed namespaces. The current milestone generates calibration trials only to verify the split mechanics; it does **not** tune policy from them yet. Held-out summaries include 95% Wilson intervals.

```bash
python experiments/run_heldout.py \
  --calibration-trials-per-scenario 50 \
  --heldout-trials-per-scenario 200
```

A zero observed FAR therefore appears as `estimate: 0`, with a positive finite-sample upper confidence bound rather than being reported as proven zero risk.

## Implemented comparators

| ID | Type | What it sees / changes |
| --- | --- | --- |
| `FULL` | verifier | current North Standard verifier |
| `B0_SELF_REPORT` | baseline | provider telemetry only |
| `B3_CHALLENGE_ONLY` | baseline | challenge scores only |
| `B5_EXTERNAL_PROBE_ONLY` | baseline | external probe result/attribution only |
| `ABLATION_NO_BINDING` | ablation | removes `session.binding` from mandatory claims |
| `ABLATION_NO_TELEMETRY` | ablation | removes telemetry evidence |
| `ABLATION_NO_EXTERNAL_PROBE` | ablation | removes external probe evidence |
| `ABLATION_NO_ABSTENTION` | ablation | converts `INCONCLUSIVE` to default `ACCEPT` |

## Challenge-aware cheating

The adversary throttles most of the delivery window but restores an honest score around challenge times it can predict.

| Schedule | Attacker knowledge |
| --- | --- |
| `fixed_periodic` | exact periodic challenge times |
| `public_jitter` | exact jittered times because schedule/seed is public |
| `hidden_jitter` | interval known but jitter draw hidden |
| `hidden_uniform` | challenge times drawn from a hidden seed |

```bash
python experiments/challenge_aware.py \
  --trials-per-schedule 100 \
  --base-seed 20260907 \
  --challenge-count 6
```

Challenge count/density are scheduling proxies only, **not measured GPU overhead**.

## Metric definitions

```text
FAR = breach trials incorrectly ACCEPTed / all breach trials
FRR = compliant trials incorrectly REJECTed / all compliant trials
IR  = INCONCLUSIVE trials / all trials
```

## Research honesty

Synthetic smoke and held-out numbers remain **pipeline diagnostics**, not evidence that North Standard detects real-world GPU cheating. Before publication/pitch claims we still need broader attack families, sensitivity analysis, measured challenge overhead, recorded-real RTX 3050 traces, limitations, and retained negative results.
