from __future__ import annotations

import unittest

from north_standard.challenge_experiment import ChallengeSchedule
from north_standard.challenge_sensitivity import run_sensitivity_grid, summarize_sensitivity


class ChallengeSensitivityTests(unittest.TestCase):
    def test_fixed_and_public_schedules_remain_fully_gameable(self) -> None:
        cells = run_sensitivity_grid(
            challenge_counts=(2, 6),
            honesty_radii_seconds=(2, 5),
            jitter_values_seconds=(10,),
            trials_per_cell=5,
            base_seed=1000,
            schedules=(ChallengeSchedule.FIXED_PERIODIC, ChallengeSchedule.PUBLIC_JITTER),
        )
        self.assertTrue(cells)
        for cell in cells:
            self.assertEqual(cell.false_accepts, cell.trials)
            self.assertEqual(cell.detected_rejects, 0)

    def test_hidden_schedules_report_bounded_intervals(self) -> None:
        cells = run_sensitivity_grid(
            challenge_counts=(2, 6),
            honesty_radii_seconds=(2, 5),
            jitter_values_seconds=(10, 20),
            trials_per_cell=8,
            base_seed=2000,
            schedules=(ChallengeSchedule.HIDDEN_JITTER, ChallengeSchedule.HIDDEN_UNIFORM),
        )
        summary = summarize_sensitivity(cells)
        self.assertFalse(summary["publication_ready"])
        for cell in summary["cells"]:
            for metric in ("false_accept_rate", "detection_rate", "inconclusive_rate"):
                interval = cell[metric]
                self.assertGreaterEqual(interval["lower"], 0.0)
                self.assertLessEqual(interval["upper"], 1.0)
                self.assertLessEqual(interval["lower"], interval["estimate"])
                self.assertGreaterEqual(interval["upper"], interval["estimate"])

    def test_invalid_jitter_radius_combinations_are_skipped(self) -> None:
        cells = run_sensitivity_grid(
            challenge_counts=(2,),
            honesty_radii_seconds=(5, 20),
            jitter_values_seconds=(10,),
            trials_per_cell=2,
            schedules=(ChallengeSchedule.HIDDEN_JITTER,),
        )
        self.assertEqual(len(cells), 1)
        self.assertEqual(cells[0].honesty_radius_seconds, 5)

    def test_grid_is_deterministic(self) -> None:
        kwargs = dict(
            challenge_counts=(4,),
            honesty_radii_seconds=(5,),
            jitter_values_seconds=(20,),
            trials_per_cell=10,
            base_seed=3000,
            schedules=(ChallengeSchedule.HIDDEN_UNIFORM,),
        )
        first = run_sensitivity_grid(**kwargs)
        second = run_sensitivity_grid(**kwargs)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
