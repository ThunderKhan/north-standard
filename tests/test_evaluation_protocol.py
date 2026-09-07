from __future__ import annotations

import unittest

from north_standard.evaluation_protocol import (
    SeedPartition,
    heldout_summary,
    run_partition,
    wilson_interval,
)
from north_standard.experiments import SyntheticCase


class EvaluationProtocolTests(unittest.TestCase):
    def test_wilson_zero_errors_retains_nonzero_upper_bound(self) -> None:
        interval = wilson_interval(0, 20)
        self.assertEqual(interval.estimate, 0.0)
        self.assertEqual(interval.lower, 0.0)
        self.assertGreater(interval.upper, 0.0)
        self.assertLess(interval.upper, 0.25)

    def test_partition_seed_sets_are_disjoint(self) -> None:
        partition = SeedPartition(
            split_id="test",
            calibration_base_seed=100,
            heldout_base_seed=10_000_100,
            calibration_trials_per_scenario=3,
            heldout_trials_per_scenario=4,
        )
        partition.assert_disjoint()
        calibration = {
            seed
            for case in SyntheticCase
            for seed in partition.seeds_for(case, heldout=False)
        }
        heldout = {
            seed
            for case in SyntheticCase
            for seed in partition.seeds_for(case, heldout=True)
        }
        self.assertFalse(calibration & heldout)

    def test_partition_is_deterministic_and_summary_has_intervals(self) -> None:
        partition = SeedPartition(
            split_id="test",
            calibration_base_seed=200,
            heldout_base_seed=20_000_200,
            calibration_trials_per_scenario=1,
            heldout_trials_per_scenario=3,
        )
        calibration_a, heldout_a = run_partition(partition)
        calibration_b, heldout_b = run_partition(partition)
        self.assertEqual(
            [(row.scenario, row.seed, row.evidence_bundle_root) for row in calibration_a],
            [(row.scenario, row.seed, row.evidence_bundle_root) for row in calibration_b],
        )
        self.assertEqual(
            [(row.scenario, row.seed, row.decision) for row in heldout_a],
            [(row.scenario, row.seed, row.decision) for row in heldout_b],
        )
        summary = heldout_summary(heldout_a, partition)
        self.assertIn("upper", summary["far"])
        self.assertIn("upper", summary["frr"])
        self.assertFalse(summary["publication_ready"])
        self.assertEqual(summary["heldout_trials"], len(SyntheticCase) * 3)

    def test_invalid_overlapping_seed_namespace_is_detected(self) -> None:
        partition = SeedPartition(
            split_id="overlap",
            calibration_base_seed=1,
            heldout_base_seed=1_000_004,
            calibration_trials_per_scenario=3,
            heldout_trials_per_scenario=3,
        )
        with self.assertRaises(ValueError):
            partition.assert_disjoint()


if __name__ == "__main__":
    unittest.main()
