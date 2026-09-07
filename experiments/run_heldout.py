#!/usr/bin/env python3
"""Run disjoint synthetic calibration/held-out seed partitions with 95% intervals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from north_standard.evaluation_protocol import (
    SeedPartition,
    heldout_summary,
    run_partition,
    write_heldout_results,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibration-trials-per-scenario", type=int, default=50)
    parser.add_argument("--heldout-trials-per-scenario", type=int, default=200)
    parser.add_argument("--calibration-base-seed", type=int, default=20_260_907)
    parser.add_argument("--heldout-base-seed", type=int, default=120_260_907)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/results/raw/heldout-synthetic"),
    )
    args = parser.parse_args()

    partition = SeedPartition(
        split_id="synthetic-v0.1-calibration-heldout",
        calibration_base_seed=args.calibration_base_seed,
        heldout_base_seed=args.heldout_base_seed,
        calibration_trials_per_scenario=args.calibration_trials_per_scenario,
        heldout_trials_per_scenario=args.heldout_trials_per_scenario,
    )
    calibration, heldout = run_partition(partition)
    paths = write_heldout_results(calibration, heldout, args.output_dir, partition)
    print(json.dumps(heldout_summary(heldout, partition), indent=2, sort_keys=True))
    print("outputs=" + ",".join(str(path) for path in paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
