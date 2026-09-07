#!/usr/bin/env python3
"""Build a Mode R calibration from explicitly designated healthy GPU captures."""

from __future__ import annotations

import argparse
import json

from north_standard.recorded_protocol import bind_calibration_to_challenge
from north_standard.recorded_real import build_calibration, load_traces, save_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("traces", nargs="+", help="healthy gpu-trace/0.1 JSON files")
    parser.add_argument("--calibration-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    traces = load_traces(args.traces)
    calibration = build_calibration(traces, calibration_id=args.calibration_id)
    calibration = bind_calibration_to_challenge(calibration, traces)
    save_json(args.output, calibration)
    print(json.dumps(calibration, indent=2, sort_keys=True))
    print(f"calibration={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
