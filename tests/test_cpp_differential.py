"""Differential tests between the Python reference verifier and the C++ core."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import unittest

from north_standard.authorization import build_settlement_authorization
from north_standard.commitment import settlement_hash
from north_standard.simulator import Scenario, simulate_scenario
from north_standard.verifier import verify


AGREEMENT_ID = "0x" + "11" * 32
VERIFIER_SET_ID = "0x" + "22" * 32


class CppDifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configured = os.environ.get("NORTH_STANDARD_CPP_CLI")
        cls.binary = Path(configured) if configured else Path("build/cpp/north-standard-cpp")
        if not cls.binary.exists():
            raise unittest.SkipTest(f"C++ verifier binary not found: {cls.binary}")

    def test_native_scenarios_match_reference_decisions(self) -> None:
        for scenario in Scenario:
            with self.subTest(scenario=scenario.value):
                contract, bundle = simulate_scenario(scenario)
                reference = verify(contract, bundle)
                completed = subprocess.run(
                    [str(self.binary), "simulate", scenario.value],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                decision_text, _, reasons_text = completed.stdout.strip().partition("|")
                cpp_reasons = tuple(filter(None, reasons_text.split(",")))
                self.assertEqual(decision_text, reference.decision.value)
                self.assertEqual(cpp_reasons, reference.reason_codes)

    def test_python_wire_input_matches_cpp_hashes_and_settlement(self) -> None:
        for scenario in Scenario:
            with self.subTest(scenario=scenario.value):
                contract, bundle = simulate_scenario(scenario)
                reference = verify(contract, bundle)
                wire_input = json.dumps(
                    {
                        "contract": contract.to_dict(),
                        "evidence_bundle": bundle.to_dict(),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                completed = subprocess.run(
                    [str(self.binary), "verify-json"],
                    input=wire_input,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                fields = completed.stdout.strip().split("|", 4)
                self.assertEqual(len(fields), 5)
                cpp_contract_hash, cpp_bundle_root, cpp_settlement_hash, cpp_decision, cpp_reasons_text = fields
                cpp_reasons = tuple(filter(None, cpp_reasons_text.split(",")))

                self.assertEqual(cpp_contract_hash, contract.semantic_hash)
                self.assertEqual(cpp_bundle_root, bundle.bundle_root)
                self.assertEqual(cpp_settlement_hash, settlement_hash(reference))
                self.assertEqual(cpp_decision, reference.decision.value)
                self.assertEqual(cpp_reasons, reference.reason_codes)

                authorization = build_settlement_authorization(
                    contract,
                    reference,
                    agreement_id=AGREEMENT_ID,
                    verifier_set_id=VERIFIER_SET_ID,
                    issued_at=1_800_000_601,
                    valid_until=1_800_001_000,
                    nonce=42,
                )
                self.assertEqual(authorization["contract_hash"], "0x" + cpp_contract_hash)
                self.assertEqual(authorization["evidence_bundle_root"], "0x" + cpp_bundle_root)
                self.assertEqual(authorization["settlement_commitment"], "0x" + cpp_settlement_hash)
                self.assertEqual(authorization["decision"], cpp_decision)


if __name__ == "__main__":
    unittest.main()
