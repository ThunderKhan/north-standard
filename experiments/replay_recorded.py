#!/usr/bin/env python3
"""Replay recorded accessible-hardware traces through the v0.1 verifier."""

from __future__ import annotations

import argparse
import json

from north_standard.policy import VerifierPolicy
from north_standard.recorded_real import (
    build_recorded_bundle,
    build_recorded_contract,
    load_json,
    load_traces,
    save_json,
)
from north_standard.verifier import verify


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("traces", nargs="+", help="recorded gpu-trace/0.1 JSON files")
    parser.add_argument("--calibration", required=True)
    parser.add_argument("--performance-floor", type=float, default=0.80)
    parser.add_argument("--output", help="optional verifier-result JSON path")
    args = parser.parse_args()

    traces = load_traces(args.traces)
    calibration = load_json(args.calibration)
    contract = build_recorded_contract(
        traces,
        performance_min_score=args.performance_floor,
    )
    bundle = build_recorded_bundle(contract, traces, calibration)
    result = verify(contract, bundle, VerifierPolicy(policy_id=contract.verifier_policy_id))

    payload = {
        "mode": "RECORDED_REAL",
        "publication_ready": False,
        "contract": contract.to_dict(),
        "evidence_bundle_root": bundle.bundle_root,
        "verifier_result": result.to_dict(),
        "limitations": [
            "The input is local software-recorded accessible-hardware evidence, not hardware attestation.",
            "The normalized performance score is calibrated only to the supplied device/profile baseline.",
            "This result is not a claim about H100-class hardware or production SLA thresholds.",
        ],
    }
    if args.output:
        save_json(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.output:
        print(f"result={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
