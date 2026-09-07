#!/usr/bin/env python3
"""Run challenge schedule sensitivity sweeps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from north_standard.challenge_sensitivity import (
    run_sensitivity_grid,
    summarize_sensitivity,
    write_sensitivity_results,
)


def _ints(value: str) -> tuple[int, ...]:
    parsed = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not parsed:
        raise argparse.ArgumentTypeError("expected at least one comma-separated integer")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--challenge-counts", type=_ints, default=(2, 4, 6, 8, 12))
    parser.add_argument("--honesty-radii-seconds", type=_ints, default=(2, 5, 10, 20))
    parser.add_argument("--jitter-values-seconds", type=_ints, default=(10, 20, 40))
    parser.add_argument("--trials-per-cell", type=int, default=100)
    parser.add_argument("--base-seed", type=int, default=320_260_907)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/results/raw/challenge-sensitivity"),
    )
    args = parser.parse_args()

    cells = run_sensitivity_grid(
        challenge_counts=args.challenge_counts,
        honesty_radii_seconds=args.honesty_radii_seconds,
        jitter_values_seconds=args.jitter_values_seconds,
        trials_per_cell=args.trials_per_cell,
        base_seed=args.base_seed,
    )
    paths = write_sensitivity_results(cells, args.output_dir)
    print(json.dumps(summarize_sensitivity(cells), indent=2, sort_keys=True))
    print("outputs=" + ",".join(str(path) for path in paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
