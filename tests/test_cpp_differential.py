"""Differential tests between the Python reference verifier and the C++ core."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest

from north_standard.simulator import Scenario, simulate_scenario
from north_standard.verifier import verify


class CppDifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configured = os.environ.get("NORTH_STANDARD_CPP_CLI")
        cls.binary = Path(configured) if configured else Path("build/cpp/north-standard-cpp")
        if not cls.binary.exists():
            raise unittest.SkipTest(f"C++ verifier binary not found: {cls.binary}")

    def test_shared_scenarios_match_python_reference(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
