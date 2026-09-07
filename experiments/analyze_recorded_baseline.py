#!/usr/bin/env python3
"""Summarize healthy Mode R capture variance without imposing a threshold."""

from __future__ import annotations

import argparse
import json

from north_standard.recorded_baseline import baseline_quality_report
from north_standard.recorded_real import load_json, load_traces, save_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("traces", nargs="+", help="healthy gpu-trace/0.1 JSON files")
    parser.add_argument("--calibration", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    traces = load_traces(args.traces)
    calibration = load_json(args.calibration)
    report = baseline_quality_report(traces, calibration)
    save_json(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"baseline_quality={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
