from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from north_standard.experiments import (
    GroundTruth,
    SyntheticCase,
    generate_case_evidence,
    run_matrix,
    run_trial,
    summarize,
    write_results,
)
from north_standard.models import Decision


class SyntheticExperimentTests(unittest.TestCase):
    def test_same_seed_reproduces_exact_evidence(self) -> None:
        contract_a, bundle_a = generate_case_evidence(SyntheticCase.MILD_THROTTLE, 4242)
        contract_b, bundle_b = generate_case_evidence(SyntheticCase.MILD_THROTTLE, 4242)
        self.assertEqual(contract_a.semantic_hash, contract_b.semantic_hash)
        self.assertEqual(bundle_a.bundle_root, bundle_b.bundle_root)

    def test_buyer_network_failure_abstains_without_calling_it_provider_fault(self) -> None:
        trial = run_trial(SyntheticCase.BUYER_NETWORK_FAILURE, 1)
        self.assertEqual(trial.ground_truth, GroundTruth.COMPLIANT)
        self.assertEqual(trial.decision, Decision.INCONCLUSIVE)
        self.assertIn("AVAILABILITY_EVIDENCE_CONFLICT", trial.reason_codes)

    def test_provider_outage_rejects(self) -> None:
        trial = run_trial(SyntheticCase.PROVIDER_OUTAGE, 1)
        self.assertEqual(trial.ground_truth, GroundTruth.BREACH)
        self.assertEqual(trial.decision, Decision.REJECT)
        self.assertIn("AVAILABILITY_PROVIDER_FAILURE", trial.reason_codes)

    def test_matrix_summary_has_expected_denominators_and_bounded_rates(self) -> None:
        trials = run_matrix(trials_per_scenario=3, base_seed=100)
        summary = summarize(trials)
        self.assertEqual(summary["total_trials"], len(SyntheticCase) * 3)
        self.assertEqual(
            summary["compliant_trials"] + summary["breach_trials"],
            summary["total_trials"],
        )
        for key in (
            "far",
            "frr",
            "inconclusive_rate",
            "inconclusive_rate_compliant",
            "inconclusive_rate_breach",
        ):
            value = summary[key]
            self.assertIsNotNone(value)
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)
        self.assertFalse(summary["publication_ready"])
        self.assertEqual(summary["status"], "SMOKE_ONLY_NOT_PUBLICATION_READY")

    def test_results_are_persisted_as_jsonl_and_summary(self) -> None:
        trials = run_matrix(trials_per_scenario=1, base_seed=7)
        with tempfile.TemporaryDirectory() as temporary:
            raw_path, summary_path = write_results(trials, Path(temporary))
            self.assertTrue(raw_path.exists())
            self.assertTrue(summary_path.exists())
            self.assertEqual(len(raw_path.read_text(encoding="utf-8").splitlines()), len(SyntheticCase))


if __name__ == "__main__":
    unittest.main()
