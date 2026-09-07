"""Example: turn a verifier result into unsigned EIP-712 signing material."""

from __future__ import annotations

import json

from north_standard.authorization import signing_package
from north_standard.simulator import Scenario, simulate_scenario
from north_standard.verifier import verify


contract, bundle = simulate_scenario(Scenario.HEALTHY_SERVICE)
result = verify(contract, bundle)

package = signing_package(
    contract,
    result,
    agreement_id="0x" + "11" * 32,
    verifier_set_id="0x" + "22" * 32,
    issued_at=1_800_000_601,
    valid_until=1_800_001_000,
    nonce=1,
    chain_id=10143,
    verifying_contract="0x" + "33" * 20,
)

print(json.dumps(package, indent=2, sort_keys=True))
