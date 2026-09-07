# Verifier Experiments

This directory is the experimental control plane for North Standard's verifier research.

## Current milestone: synthetic smoke harnesses

The current harnesses are intentionally **not benchmark results**. They prove that the repository can:

1. generate seeded evidence without exposing ground truth to the verifier;
2. retain explicit `COMPLIANT` / `BREACH` labels only in the experiment harness;
3. run the same deterministic verifier used by the settlement path;
4. persist per-trial raw records;
5. calculate FAR, FRR, and INCONCLUSIVE rates with explicit denominators;
6. compare the full verifier against explicit evidence-subset baselines and verifier ablations;
7. model a challenge-aware cheating provider under predictable versus hidden challenge schedules.

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

Run:

```bash
python -m pip install -e .
python experiments/run_synthetic.py --trials-per-scenario 25 --base-seed 20260907
python experiments/compare_evaluators.py --trials-per-scenario 25 --base-seed 20260907
```

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

The B0/B3/B5 labels refer specifically to these implemented comparators. They do not imply the full production behavior of any external system.

## Challenge-aware cheating

The adversary throttles most of the delivery window but restores an honest score inside a small window around challenge times it can predict.

Schedules:

| Schedule | Attacker knowledge |
| --- | --- |
| `fixed_periodic` | exact periodic challenge times |
| `public_jitter` | exact jittered times because the schedule/seed is public |
| `hidden_jitter` | interval is known but jitter draw is hidden |
| `hidden_uniform` | challenge times are drawn uniformly from a hidden seed |

Run:

```bash
python experiments/challenge_aware.py \
  --trials-per-schedule 100 \
  --base-seed 20260907 \
  --challenge-count 6
```

The primary smoke metric here is **false-accept rate under known cheating**. `REJECT` is counted as detected; `INCONCLUSIVE` remains separate rather than being silently counted as success.

Challenge count and density are scheduling proxies only. They are **not measured GPU overhead**. Actual challenge-runtime overhead will come from recorded-real hardware work later.

## Metric definitions

```text
FAR = breach trials incorrectly ACCEPTed / all breach trials
FRR = compliant trials incorrectly REJECTed / all compliant trials
IR  = INCONCLUSIVE trials / all trials
```

## Research honesty

Any numbers produced by these smoke harnesses are **synthetic pipeline diagnostics**. They are not final evidence that North Standard detects real provider cheating. Before numbers become research/pitch claims we still need, at minimum:

- a frozen held-out attack suite;
- confidence intervals and exact sample counts;
- sensitivity sweeps over challenge frequency and attacker honesty windows;
- measured challenge runtime/overhead;
- recorded-real RTX 3050 traces;
- limitations and negative-result retention.
