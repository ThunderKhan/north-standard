#!/usr/bin/env python3
"""Run the synthetic challenge-aware cheating schedule comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from north_standard.challenge_experiment import (
    ChallengeExperimentConfig,
    run_challenge_matrix,
    summarize_challenge_matrix,
    write_challenge_results,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials-per-schedule", type=int, default=100)
    parser.add_argument("--base-seed", type=int, default=20260907)
    parser.add_argument("--challenge-count", type=int, default=6)
    parser.add_argument("--honesty-radius-seconds", type=int, default=5)
    parser.add_argument("--jitter-seconds", type=int, default=20)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/results/raw/challenge-aware"),
    )
    args = parser.parse_args()

    config = ChallengeExperimentConfig(
        challenge_count=args.challenge_count,
        honesty_radius_seconds=args.honesty_radius_seconds,
        jitter_seconds=args.jitter_seconds,
    )
    rows = run_challenge_matrix(
        trials_per_schedule=args.trials_per_schedule,
        base_seed=args.base_seed,
        config=config,
    )
    raw_path, summary_path = write_challenge_results(rows, args.output_dir, config)
    print(json.dumps(summarize_challenge_matrix(rows, config), indent=2, sort_keys=True))
    print(f"raw_trials={raw_path}")
    print(f"summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
