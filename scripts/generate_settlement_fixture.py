#!/usr/bin/env python3
"""Generate Solidity fixtures from the real North Standard verifier pipeline.

The generator runs the Python reference verifier for the four Step-1 scenarios and,
when requested, verifies every settlement-critical field against the C++20 core.
The resulting Solidity library is consumed by the Foundry end-to-end settlement test.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from north_standard.authorization import build_settlement_authorization
from north_standard.commitment import settlement_hash
from north_standard.models import Decision
from north_standard.simulator import Scenario, simulate_scenario
from north_standard.verifier import verify


SCENARIOS = (
    (Scenario.HEALTHY_SERVICE, "HEALTHY", "11", 101),
    (Scenario.REPLAYED_EVIDENCE, "REPLAYED", "12", 102),
    (Scenario.CONSTANT_THROTTLE, "THROTTLE", "13", 103),
    (Scenario.AMBIGUOUS_NETWORK_FAILURE, "AMBIGUOUS", "14", 104),
)
VERIFIER_SET_ID = "0x" + "22" * 32
ISSUED_AT = 1_800_000_601
VALID_UNTIL = 1_800_004_200
DECISION_UINT8 = {
    Decision.ACCEPT: 0,
    Decision.REJECT: 1,
    Decision.INCONCLUSIVE: 2,
}


def _wire_json(contract, bundle) -> str:
    return json.dumps(
        {"contract": contract.to_dict(), "evidence_bundle": bundle.to_dict()},
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _cpp_result(binary: Path, contract, bundle) -> tuple[str, str, str, str, tuple[str, ...]]:
    completed = subprocess.run(
        [str(binary), "verify-json"],
        input=_wire_json(contract, bundle),
        check=True,
        capture_output=True,
        text=True,
    )
    fields = completed.stdout.strip().split("|", 4)
    if len(fields) != 5:
        raise RuntimeError(f"unexpected C++ verify-json output: {completed.stdout!r}")
    contract_hash, evidence_root, settlement_commitment, decision, reasons_text = fields
    return (
        contract_hash,
        evidence_root,
        settlement_commitment,
        decision,
        tuple(filter(None, reasons_text.split(","))),
    )


def generate(cpp_cli: Path | None, require_cpp: bool) -> str:
    if require_cpp and (cpp_cli is None or not cpp_cli.exists()):
        raise FileNotFoundError(f"C++ verifier binary not found: {cpp_cli}")

    rows: list[dict[str, object]] = []
    shared: dict[str, str] | None = None

    for scenario, label, agreement_byte, nonce in SCENARIOS:
        contract, bundle = simulate_scenario(scenario)
        result = verify(contract, bundle)
        authorization = build_settlement_authorization(
            contract,
            result,
            agreement_id="0x" + agreement_byte * 32,
            verifier_set_id=VERIFIER_SET_ID,
            issued_at=ISSUED_AT,
            valid_until=VALID_UNTIL,
            nonce=nonce,
        )

        if cpp_cli is not None and cpp_cli.exists():
            cpp_contract, cpp_evidence, cpp_settlement, cpp_decision, cpp_reasons = _cpp_result(
                cpp_cli, contract, bundle
            )
            expected_reasons = tuple(result.reason_codes)
            mismatches = []
            if cpp_contract != contract.semantic_hash:
                mismatches.append("contract_hash")
            if cpp_evidence != bundle.bundle_root:
                mismatches.append("evidence_bundle_root")
            if cpp_settlement != settlement_hash(result):
                mismatches.append("settlement_commitment")
            if cpp_decision != result.decision.value:
                mismatches.append("decision")
            if cpp_reasons != expected_reasons:
                mismatches.append("reason_codes")
            if mismatches:
                raise RuntimeError(
                    f"Python/C++ mismatch for {scenario.value}: {', '.join(mismatches)}"
                )

        current_shared = {
            "contract_hash": authorization["contract_hash"],
            "verifier_policy_hash": authorization["verifier_policy_hash"],
            "settlement_policy_hash": authorization["settlement_policy_hash"],
            "verifier_set_id": authorization["verifier_set_id"],
        }
        if shared is None:
            shared = current_shared
        elif shared != current_shared:
            raise RuntimeError("shared agreement binding fields changed across scenario fixtures")

        rows.append(
            {
                "label": label,
                "scenario": scenario.value,
                "agreement_id": authorization["agreement_id"],
                "settlement_commitment": authorization["settlement_commitment"],
                "evidence_bundle_root": authorization["evidence_bundle_root"],
                "decision": DECISION_UINT8[result.decision],
                "nonce": nonce,
            }
        )

    assert shared is not None
    lines = [
        "// SPDX-License-Identifier: Apache-2.0",
        "pragma solidity ^0.8.28;",
        "",
        "// AUTO-GENERATED by scripts/generate_settlement_fixture.py.",
        "// Do not hand-edit: these values come from the Python verifier and are parity-checked against C++ in CI.",
        "library GeneratedVerifierSettlementFixtures {",
        f"    bytes32 internal constant CONTRACT_HASH = {shared['contract_hash']};",
        f"    bytes32 internal constant VERIFIER_POLICY_HASH = {shared['verifier_policy_hash']};",
        f"    bytes32 internal constant SETTLEMENT_POLICY_HASH = {shared['settlement_policy_hash']};",
        f"    bytes32 internal constant VERIFIER_SET_ID = {shared['verifier_set_id']};",
        f"    uint64 internal constant ISSUED_AT = {ISSUED_AT};",
        f"    uint64 internal constant VALID_UNTIL = {VALID_UNTIL};",
        "",
    ]
    for row in rows:
        label = row["label"]
        lines.extend(
            [
                f"    // {row['scenario']}",
                f"    bytes32 internal constant {label}_AGREEMENT_ID = {row['agreement_id']};",
                f"    bytes32 internal constant {label}_SETTLEMENT_COMMITMENT = {row['settlement_commitment']};",
                f"    bytes32 internal constant {label}_EVIDENCE_BUNDLE_ROOT = {row['evidence_bundle_root']};",
                f"    uint8 internal constant {label}_DECISION = {row['decision']};",
                f"    uint256 internal constant {label}_NONCE = {row['nonce']};",
                "",
            ]
        )
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("contracts/test/generated/GeneratedVerifierSettlementFixtures.sol"),
    )
    parser.add_argument(
        "--cpp-cli",
        type=Path,
        default=Path(os.environ.get("NORTH_STANDARD_CPP_CLI", "build/cpp/north-standard-cpp")),
    )
    parser.add_argument("--require-cpp", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    content = generate(args.cpp_cli, args.require_cpp)
    if args.check:
        if not args.output.exists():
            print(f"missing generated fixture: {args.output}", file=sys.stderr)
            return 1
        if args.output.read_text(encoding="utf-8") != content:
            print(f"stale generated fixture: {args.output}", file=sys.stderr)
            return 1
        print(f"fixture is current: {args.output}")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
