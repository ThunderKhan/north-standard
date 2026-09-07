# Verifier Experiments

This directory is the experimental control plane for North Standard's verifier research.

## Current milestone: reproducible synthetic evaluation plumbing

The current harnesses are intentionally **not benchmark results**. They support:

1. seeded evidence with hidden ground truth outside the verifier;
2. FAR, FRR, and INCONCLUSIVE rates with explicit denominators;
3. evidence-subset baselines and verifier ablations;
4. challenge-aware cheating under predictable versus hidden schedules;
5. disjoint calibration/held-out seed namespaces;
6. 95% Wilson intervals so zero observed errors are never presented as zero uncertainty;
7. sensitivity sweeps over challenge frequency, attacker honesty windows, and jitter width.

## General synthetic matrix

Current families include healthy variance, marginal healthy behavior, mild/severe throttling, replayed evidence, buyer-network failure, provider outage, and telemetry gaps.

```bash
python experiments/run_synthetic.py --trials-per-scenario 25 --base-seed 20260907
python experiments/compare_evaluators.py --trials-per-scenario 25 --base-seed 20260907
```

## Held-out protocol

Calibration and held-out runs use separate deterministic seed namespaces. This milestone does not tune policy from calibration data yet. Held-out summaries include 95% Wilson intervals.

```bash
python experiments/run_heldout.py \
  --calibration-trials-per-scenario 50 \
  --heldout-trials-per-scenario 200
```

A zero observed FAR therefore retains a positive finite-sample upper confidence bound.

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
python experiments/challenge_aware.py --trials-per-schedule 100 --challenge-count 6
```

## Challenge sensitivity

The sensitivity grid deliberately varies the assumptions that can make randomized challenge systems look better or worse:

```bash
python experiments/challenge_sensitivity.py \
  --challenge-counts 2,4,6,8,12 \
  --honesty-radii-seconds 2,5,10,20 \
  --jitter-values-seconds 10,20,40 \
  --trials-per-cell 100
```

Every parameter cell reports Wilson intervals for false accept, detection, and abstention. Invalid cells where the jitter width is smaller than the modeled honesty window are skipped rather than silently coerced.

Challenge count/density are scheduling proxies only, **not measured GPU overhead**.

## Metric definitions

```text
FAR = breach trials incorrectly ACCEPTed / all breach trials
FRR = compliant trials incorrectly REJECTed / all compliant trials
IR  = INCONCLUSIVE trials / all trials
```

## Research honesty

Synthetic smoke, held-out, and sensitivity numbers remain **pipeline diagnostics**, not evidence that North Standard detects real-world GPU cheating. Before publication/pitch claims we still need broader attack families, measured challenge overhead, recorded-real RTX 3050 traces, limitations, and retained negative results.
