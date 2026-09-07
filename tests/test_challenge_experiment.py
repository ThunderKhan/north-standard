from __future__ import annotations

import unittest

from north_standard.challenge_experiment import (
    ChallengeExperimentConfig,
    ChallengeSchedule,
    run_challenge_matrix,
    run_challenge_trial,
    summarize_challenge_matrix,
)
from north_standard.models import Decision


class ChallengeAwareExperimentTests(unittest.TestCase):
    def test_fixed_periodic_is_fully_evaded_by_schedule_aware_attacker(self) -> None:
        trial = run_challenge_trial(ChallengeSchedule.FIXED_PERIODIC, 1)
        self.assertEqual(trial.breach_challenges, 0)
        self.assertGreater(trial.estimated_cheat_fraction, 0.5)
        self.assertEqual(trial.decision, Decision.ACCEPT)

    def test_public_jitter_is_still_evaded_when_attacker_knows_schedule(self) -> None:
        trial = run_challenge_trial(ChallengeSchedule.PUBLIC_JITTER, 123)
        self.assertEqual(trial.actual_challenge_times, trial.attacker_predicted_times)
        self.assertEqual(trial.breach_challenges, 0)
        self.assertEqual(trial.decision, Decision.ACCEPT)

    def test_hidden_uniform_materially_reduces_false_accepts_in_smoke_sweep(self) -> None:
        config = ChallengeExperimentConfig()
        rows = run_challenge_matrix(
            trials_per_schedule=50,
            base_seed=9000,
            config=config,
        )
        summary = summarize_challenge_matrix(rows, config)
        fixed = summary["schedules"][ChallengeSchedule.FIXED_PERIODIC.value]
        hidden = summary["schedules"][ChallengeSchedule.HIDDEN_UNIFORM.value]
        self.assertEqual(fixed["false_accept_rate"], 1.0)
        self.assertLess(hidden["false_accept_rate"], fixed["false_accept_rate"])
        self.assertGreater(hidden["detection_rate"], 0.0)
        self.assertFalse(summary["publication_ready"])

    def test_hidden_jitter_can_create_breach_challenges(self) -> None:
        trials = [
            run_challenge_trial(ChallengeSchedule.HIDDEN_JITTER, seed)
            for seed in range(30)
        ]
        self.assertTrue(any(trial.breach_challenges >= 2 for trial in trials))


if __name__ == "__main__":
    unittest.main()
