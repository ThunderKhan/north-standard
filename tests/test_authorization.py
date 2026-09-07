from __future__ import annotations

from hashlib import sha256
import unittest

from north_standard.authorization import (
    build_settlement_authorization,
    eip712_typed_data,
    signing_package,
)
from north_standard.commitment import settlement_hash
from north_standard.simulator import Scenario, simulate_scenario
from north_standard.verifier import verify


AGREEMENT_ID = "0x" + "11" * 32
VERIFIER_SET_ID = "0x" + "22" * 32
VERIFYING_CONTRACT = "0x" + "33" * 20


class AuthorizationTests(unittest.TestCase):
    def test_authorization_binds_verifier_and_settlement_hashes(self) -> None:
        contract, bundle = simulate_scenario(Scenario.HEALTHY_SERVICE)
        result = verify(contract, bundle)
        auth = build_settlement_authorization(
            contract,
            result,
            agreement_id=AGREEMENT_ID,
            verifier_set_id=VERIFIER_SET_ID,
            issued_at=1_800_000_601,
            valid_until=1_800_001_000,
            nonce=7,
        )

        self.assertEqual(auth["contract_hash"], "0x" + contract.semantic_hash)
        self.assertEqual(auth["settlement_commitment"], "0x" + settlement_hash(result))
        self.assertEqual(auth["evidence_bundle_root"], "0x" + bundle.bundle_root)
        self.assertEqual(
            auth["verifier_policy_hash"],
            "0x" + sha256(contract.verifier_policy_id.encode()).hexdigest(),
        )
        self.assertEqual(
            auth["settlement_policy_hash"],
            "0x" + sha256(contract.settlement_policy_id.encode()).hexdigest(),
        )
        self.assertEqual(auth["decision"], "ACCEPT")

    def test_typed_data_matches_solidity_field_names_and_decision_enum(self) -> None:
        contract, bundle = simulate_scenario(Scenario.CONSTANT_THROTTLE)
        result = verify(contract, bundle)
        auth = build_settlement_authorization(
            contract,
            result,
            agreement_id=AGREEMENT_ID,
            verifier_set_id=VERIFIER_SET_ID,
            issued_at=1,
            valid_until=2,
            nonce=9,
        )
        typed = eip712_typed_data(auth, chain_id=10143, verifying_contract=VERIFYING_CONTRACT)

        self.assertEqual(typed["primaryType"], "SettlementAuthorization")
        self.assertEqual(typed["domain"]["name"], "North Standard Settlement")
        self.assertEqual(typed["domain"]["version"], "0.1")
        self.assertEqual(typed["domain"]["chainId"], 10143)
        self.assertEqual(typed["message"]["decision"], 1)
        self.assertEqual(typed["message"]["contractHash"], auth["contract_hash"])
        self.assertEqual(typed["message"]["settlementCommitment"], auth["settlement_commitment"])

    def test_inconclusive_maps_to_uint8_two(self) -> None:
        contract, bundle = simulate_scenario(Scenario.AMBIGUOUS_NETWORK_FAILURE)
        result = verify(contract, bundle)
        package = signing_package(
            contract,
            result,
            agreement_id=AGREEMENT_ID,
            verifier_set_id=VERIFIER_SET_ID,
            issued_at=10,
            valid_until=20,
            nonce=1,
            chain_id=10143,
            verifying_contract=VERIFYING_CONTRACT,
        )
        self.assertEqual(package["authorization"]["decision"], "INCONCLUSIVE")
        self.assertEqual(package["eip712_typed_data"]["message"]["decision"], 2)

    def test_invalid_time_window_rejected(self) -> None:
        contract, bundle = simulate_scenario(Scenario.HEALTHY_SERVICE)
        result = verify(contract, bundle)
        with self.assertRaises(ValueError):
            build_settlement_authorization(
                contract,
                result,
                agreement_id=AGREEMENT_ID,
                verifier_set_id=VERIFIER_SET_ID,
                issued_at=20,
                valid_until=19,
                nonce=0,
            )

    def test_invalid_address_rejected(self) -> None:
        contract, bundle = simulate_scenario(Scenario.HEALTHY_SERVICE)
        result = verify(contract, bundle)
        auth = build_settlement_authorization(
            contract,
            result,
            agreement_id=AGREEMENT_ID,
            verifier_set_id=VERIFIER_SET_ID,
            issued_at=1,
            valid_until=2,
            nonce=0,
        )
        with self.assertRaises(ValueError):
            eip712_typed_data(auth, chain_id=10143, verifying_contract="0x1234")


if __name__ == "__main__":
    unittest.main()
