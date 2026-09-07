from __future__ import annotations

import unittest

from north_standard.evaluators import (
    DEFAULT_EVALUATORS,
    Evaluator,
    evaluate,
    run_comparison_matrix,
    summarize_comparison,
)
from north_standard.experiments import SyntheticCase, generate_case_evidence
from north_standard.models import Decision


class EvaluatorTests(unittest.TestCase):
    def test_binding_ablation_exposes_replay_attack(self) -> None:
        contract, bundle = generate_case_evidence(SyntheticCase.REPLAYED_EVIDENCE, 1)
        self.assertEqual(evaluate(Evaluator.FULL, contract, bundle).decision, Decision.REJECT)
        self.assertEqual(
            evaluate(Evaluator.ABLATION_NO_BINDING, contract, bundle).decision,
            Decision.ACCEPT,
        )

    def test_self_report_misses_throttle(self) -> None:
        contract, bundle = generate_case_evidence(SyntheticCase.SEVERE_THROTTLE, 2)
        self.assertEqual(evaluate(Evaluator.FULL, contract, bundle).decision, Decision.REJECT)
        self.assertEqual(
            evaluate(Evaluator.B0_SELF_REPORT, contract, bundle).decision,
            Decision.ACCEPT,
        )

    def test_external_probe_detects_provider_outage(self) -> None:
        contract, bundle = generate_case_evidence(SyntheticCase.PROVIDER_OUTAGE, 3)
        self.assertEqual(
            evaluate(Evaluator.B5_EXTERNAL_PROBE_ONLY, contract, bundle).decision,
            Decision.REJECT,
        )

    def test_disabling_abstention_accepts_ambiguous_buyer_network_failure(self) -> None:
        contract, bundle = generate_case_evidence(SyntheticCase.BUYER_NETWORK_FAILURE, 4)
        self.assertEqual(evaluate(Evaluator.FULL, contract, bundle).decision, Decision.INCONCLUSIVE)
        no_abstention = evaluate(Evaluator.ABLATION_NO_ABSTENTION, contract, bundle)
        self.assertEqual(no_abstention.decision, Decision.ACCEPT)
        self.assertIn("ABSTENTION_DISABLED_ACCEPT_DEFAULT", no_abstention.reason_codes)

    def test_comparison_summary_covers_all_default_evaluators(self) -> None:
        rows = run_comparison_matrix(trials_per_scenario=1, base_seed=50)
        summary = summarize_comparison(rows)
        self.assertEqual(set(summary["evaluators"]), {item.value for item in DEFAULT_EVALUATORS})
        self.assertFalse(summary["publication_ready"])
        for metrics in summary["evaluators"].values():
            for key in ("far", "frr", "inconclusive_rate"):
                value = metrics[key]
                self.assertIsNotNone(value)
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)


if __name__ == "__main__":
    unittest.main()
