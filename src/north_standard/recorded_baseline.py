"""Descriptive baseline-quality analysis for Mode R.

This module deliberately does not decide whether a baseline is "stable enough".
It reports robust dispersion and run-to-run drift so thresholds can be justified
from observed hardware data instead of invented before the first physical capture.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Sequence

from .recorded_protocol import validate_challenge_binding
from .recorded_real import (
    RECORDED_REAL,
    RecordedRealError,
    device_fingerprint,
    validate_calibration,
    validate_trace,
)

BASELINE_REPORT_SCHEMA_VERSION = "recorded-baseline-quality/0.1"
BASELINE_REPORT_STATUS = "DESCRIPTIVE_ONLY_NO_STABILITY_THRESHOLD"


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValueError("quantile requires at least one value")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be in [0, 1]")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _distribution(values: Sequence[float]) -> dict[str, float | int]:
    if not values:
        raise ValueError("distribution requires at least one value")
    numeric = [float(value) for value in values]
    if any(not math.isfinite(value) for value in numeric):
        raise ValueError("distribution values must be finite")
    median = statistics.median(numeric)
    absolute_deviations = [abs(value - median) for value in numeric]
    mad = statistics.median(absolute_deviations)
    p10 = _quantile(numeric, 0.10)
    p90 = _quantile(numeric, 0.90)
    span = p90 - p10
    return {
        "count": len(numeric),
        "minimum": min(numeric),
        "p10": p10,
        "median": median,
        "p90": p90,
        "maximum": max(numeric),
        "mad": mad,
        "relative_mad": mad / abs(median) if median != 0.0 else math.inf,
        "interdecile_span": span,
        "relative_interdecile_span": span / abs(median) if median != 0.0 else math.inf,
    }


def _relative_deviation(value: float, reference: float) -> float:
    if reference == 0.0:
        return math.inf if value != 0.0 else 0.0
    return abs(value - reference) / abs(reference)


def _run_to_run(trace_medians: Sequence[float]) -> dict[str, Any]:
    distribution = _distribution(trace_medians)
    global_median = float(distribution["median"])
    deviations = [
        _relative_deviation(float(value), global_median) for value in trace_medians
    ]
    return {
        "trace_medians": [float(value) for value in trace_medians],
        "median_of_trace_medians": global_median,
        "maximum_relative_deviation_from_median": max(deviations),
        "median_relative_deviation_from_median": statistics.median(deviations),
    }


def baseline_quality_report(
    traces: Sequence[dict[str, Any]],
    calibration: dict[str, Any],
) -> dict[str, Any]:
    if len(traces) < 3:
        raise RecordedRealError(
            "baseline-quality analysis requires at least three healthy captures"
        )
    validate_calibration(calibration)
    validate_challenge_binding(calibration, traces)

    expected_fingerprint = calibration.get("device_fingerprint")
    expected_runtime = calibration.get("runtime_profile_id")
    expected_benchmark = calibration.get("benchmark_profile_id")

    compute_samples: list[float] = []
    memory_samples: list[float] = []
    runtime_samples: list[float] = []
    compute_trace_medians: list[float] = []
    memory_trace_medians: list[float] = []
    runtime_trace_medians: list[float] = []

    for trace in traces:
        validate_trace(trace)
        if device_fingerprint(trace) != expected_fingerprint:
            raise RecordedRealError("baseline trace device does not match calibration")
        if trace["runtime_profile_id"] != expected_runtime:
            raise RecordedRealError("baseline trace runtime profile does not match calibration")
        if trace["benchmark_profile_id"] != expected_benchmark:
            raise RecordedRealError("baseline trace benchmark profile does not match calibration")

        trace_compute = [float(sample["compute_gflops"]) for sample in trace["samples"]]
        trace_memory = [float(sample["memory_gbps"]) for sample in trace["samples"]]
        trace_runtime = [
            float(sample["compute_ms"]) + float(sample["memory_ms"])
            for sample in trace["samples"]
        ]

        compute_samples.extend(trace_compute)
        memory_samples.extend(trace_memory)
        runtime_samples.extend(trace_runtime)
        compute_trace_medians.append(statistics.median(trace_compute))
        memory_trace_medians.append(statistics.median(trace_memory))
        runtime_trace_medians.append(statistics.median(trace_runtime))

    return {
        "schema_version": BASELINE_REPORT_SCHEMA_VERSION,
        "mode": RECORDED_REAL,
        "status": BASELINE_REPORT_STATUS,
        "publication_ready": False,
        "calibration_id": calibration["calibration_id"],
        "device_fingerprint": expected_fingerprint,
        "runtime_profile_id": expected_runtime,
        "benchmark_profile_id": expected_benchmark,
        "challenge_fingerprint": calibration.get("challenge_fingerprint"),
        "trace_count": len(traces),
        "sample_count": len(compute_samples),
        "capture_ids": [str(trace["capture_id"]) for trace in traces],
        "metrics": {
            "compute_gflops": {
                "all_samples": _distribution(compute_samples),
                "run_to_run": _run_to_run(compute_trace_medians),
            },
            "memory_gbps": {
                "all_samples": _distribution(memory_samples),
                "run_to_run": _run_to_run(memory_trace_medians),
            },
            "challenge_runtime_ms": {
                "all_samples": _distribution(runtime_samples),
                "run_to_run": _run_to_run(runtime_trace_medians),
            },
        },
        "notes": [
            "This report is descriptive only and intentionally contains no pass/fail stability threshold.",
            "MAD means median absolute deviation; relative MAD divides MAD by the metric median.",
            "Run-to-run drift is computed from each capture's median, not from individual samples pooled across captures.",
            "A stability threshold, if later introduced, must be justified from observed data and documented before held-out evaluation.",
            "The measurements describe only the recorded accessible device/profile and are not H100/H200/B200 claims.",
        ],
    }
