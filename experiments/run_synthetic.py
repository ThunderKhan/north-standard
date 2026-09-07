#!/usr/bin/env python3
"""Run the synthetic smoke experiment matrix and persist raw + derived outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from north_standard.experiments import run_matrix, summarize, write_results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials-per-scenario", type=int, default=25)
    parser.add_argument("--base-seed", type=int, default=20260907)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/results/raw/synthetic-smoke"),
    )
    args = parser.parse_args()

    trials = run_matrix(
        trials_per_scenario=args.trials_per_scenario,
        base_seed=args.base_seed,
    )
    raw_path, summary_path = write_results(trials, args.output_dir)
    summary = summarize(trials)
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"raw_trials={raw_path}")
    print(f"summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
