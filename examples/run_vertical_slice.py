"""Run all four Step-1 scenarios and print their decisions."""

from north_standard.simulator import Scenario, simulate_scenario
from north_standard.verifier import verify


for scenario in Scenario:
    contract, bundle = simulate_scenario(scenario)
    result = verify(contract, bundle)
    print(f"{scenario.value:28} -> {result.decision.value:12} {', '.join(result.reason_codes)}")
