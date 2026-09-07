import unittest

from north_standard.models import ClaimState, Decision, EvidenceBundle
from north_standard.policy import VerifierPolicy
from north_standard.simulator import Scenario, demo_contract, simulate_scenario
from north_standard.verifier import verify


class VerifierScenarioTests(unittest.TestCase):
    def test_healthy_service_accepts(self) -> None:
        contract, bundle = simulate_scenario(Scenario.HEALTHY_SERVICE)
        result = verify(contract, bundle)
        self.assertEqual(result.decision, Decision.ACCEPT)
        self.assertTrue(
            all(claim.state == ClaimState.AFFIRMING for claim in result.claims.values())
        )

    def test_replayed_evidence_rejects(self) -> None:
        contract, bundle = simulate_scenario(Scenario.REPLAYED_EVIDENCE)
        result = verify(contract, bundle)
        self.assertEqual(result.decision, Decision.REJECT)
        self.assertEqual(result.claims["session.binding"].state, ClaimState.CONTRADICTING)
        self.assertIn("SESSION_ID_MISMATCH", result.reason_codes)

    def test_constant_throttle_rejects(self) -> None:
        contract, bundle = simulate_scenario(Scenario.CONSTANT_THROTTLE)
        result = verify(contract, bundle)
        self.assertEqual(result.decision, Decision.REJECT)
        performance = result.claims["service.performance"]
        self.assertEqual(performance.state, ClaimState.CONTRADICTING)
        self.assertIn("CHALLENGE_PERFORMANCE_BREACH", performance.reason_codes)

    def test_ambiguous_network_failure_abstains(self) -> None:
        contract, bundle = simulate_scenario(Scenario.AMBIGUOUS_NETWORK_FAILURE)
        result = verify(contract, bundle)
        self.assertEqual(result.decision, Decision.INCONCLUSIVE)
        availability = result.claims["service.availability"]
        self.assertEqual(availability.state, ClaimState.UNKNOWN)
        self.assertIn("AVAILABILITY_EVIDENCE_CONFLICT", availability.reason_codes)

    def test_verifier_is_deterministic(self) -> None:
        contract, bundle = simulate_scenario(Scenario.HEALTHY_SERVICE)
        left = verify(contract, bundle)
        right = verify(contract, bundle)
        self.assertEqual(left.result_hash, right.result_hash)
        self.assertEqual(left.evidence_bundle_root, right.evidence_bundle_root)

    def test_duplicate_evidence_id_is_fatal(self) -> None:
        contract, bundle = simulate_scenario(Scenario.HEALTHY_SERVICE)
        duplicate_records = bundle.records + (bundle.records[0],)
        tampered_bundle = EvidenceBundle(
            contract_id=contract.contract_id,
            session_id=contract.session_id,
            records=duplicate_records,
        )
        result = verify(contract, tampered_bundle)
        self.assertEqual(result.decision, Decision.REJECT)
        self.assertIn("DUPLICATE_EVIDENCE_ID", result.reason_codes)

    def test_policy_mismatch_is_rejected_before_appraisal(self) -> None:
        contract = demo_contract()
        _, bundle = simulate_scenario(Scenario.HEALTHY_SERVICE, contract)
        wrong_policy = VerifierPolicy(policy_id="OTHER")
        with self.assertRaises(ValueError):
            verify(contract, bundle, wrong_policy)


if __name__ == "__main__":
    unittest.main()
