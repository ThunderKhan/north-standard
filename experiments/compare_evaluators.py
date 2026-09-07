#!/usr/bin/env python3
"""Compare the full verifier with explicit baselines and ablations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from north_standard.evaluators import (
    run_comparison_matrix,
    summarize_comparison,
    write_comparison_results,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials-per-scenario", type=int, default=25)
    parser.add_argument("--base-seed", type=int, default=20260907)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/results/raw/evaluator-comparison"),
    )
    args = parser.parse_args()

    rows = run_comparison_matrix(
        trials_per_scenario=args.trials_per_scenario,
        base_seed=args.base_seed,
    )
    raw_path, summary_path = write_comparison_results(rows, args.output_dir)
    print(json.dumps(summarize_comparison(rows), indent=2, sort_keys=True))
    print(f"raw_trials={raw_path}")
    print(f"summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
