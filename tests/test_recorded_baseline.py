from __future__ import annotations

import copy
import unittest

from north_standard.recorded_baseline import baseline_quality_report
from north_standard.recorded_protocol import bind_calibration_to_challenge
from north_standard.recorded_real import RecordedRealError, build_calibration


def make_trace(
    capture_id: str,
    *,
    compute: tuple[float, ...],
    memory: tuple[float, ...],
    runtime_ms: tuple[float, ...],
    captured_at_ms: int,
) -> dict:
    samples = []
    for index, (compute_value, memory_value, total_runtime) in enumerate(
        zip(compute, memory, runtime_ms, strict=True)
    ):
        samples.append(
            {
                "sample_index": index,
                "observed_at_unix_ms": captured_at_ms + index * 1000,
                "compute_ms": total_runtime * 0.6,
                "compute_gflops": compute_value,
                "memory_ms": total_runtime * 0.4,
                "memory_gbps": memory_value,
            }
        )
    return {
        "schema_version": "gpu-trace/0.1",
        "provenance": "RECORDED_REAL",
        "capture_id": capture_id,
        "captured_at_unix_ms": captured_at_ms,
        "contract_id": "baseline-contract",
        "session_id": "baseline-session",
        "runtime_profile_id": "CUDA-RECORDED-v0.1",
        "benchmark_profile_id": "CUDA-MICROBENCH-v0.2",
        "collector": {
            "name": "north-standard-cuda-probe",
            "version": "0.2",
            "authentication": "LOCAL_SOFTWARE_ONLY",
        },
        "device": {
            "ordinal": 0,
            "name": "TEST GPU - NOT EMPIRICAL",
            "compute_capability_major": 8,
            "compute_capability_minor": 6,
            "global_memory_bytes": 4_294_967_296,
            "multiprocessor_count": 20,
            "max_clock_khz": 1_500_000,
            "memory_clock_khz": 6_000_000,
            "memory_bus_width_bits": 128,
            "cuda_runtime_version": 12080,
            "cuda_driver_version": 12080,
        },
        "challenge": {
            "elements": 1_048_576,
            "compute_inner_iterations": 128,
            "warmup_iterations": 3,
            "measurement_iterations": len(samples),
        },
        "samples": samples,
        "limitations": ["Unit-test fixture; not physical evidence."],
    }


class RecordedBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.traces = [
            make_trace(
                "healthy-1",
                compute=(98.0, 100.0, 102.0),
                memory=(196.0, 200.0, 204.0),
                runtime_ms=(2.0, 2.1, 2.0),
                captured_at_ms=1_800_000_000_000,
            ),
            make_trace(
                "healthy-2",
                compute=(99.0, 101.0, 103.0),
                memory=(198.0, 202.0, 206.0),
                runtime_ms=(2.1, 2.0, 2.2),
                captured_at_ms=1_800_000_010_000,
            ),
            make_trace(
                "healthy-3",
                compute=(97.0, 99.0, 101.0),
                memory=(194.0, 198.0, 202.0),
                runtime_ms=(1.9, 2.0, 2.1),
                captured_at_ms=1_800_000_020_000,
            ),
        ]
        calibration = build_calibration(self.traces, calibration_id="healthy-cal")
        self.calibration = bind_calibration_to_challenge(calibration, self.traces)

    def test_report_is_descriptive_and_exposes_robust_dispersion(self) -> None:
        report = baseline_quality_report(self.traces, self.calibration)
        self.assertEqual(report["status"], "DESCRIPTIVE_ONLY_NO_STABILITY_THRESHOLD")
        self.assertFalse(report["publication_ready"])
        self.assertEqual(report["trace_count"], 3)
        self.assertEqual(report["sample_count"], 9)
        compute = report["metrics"]["compute_gflops"]
        self.assertAlmostEqual(compute["all_samples"]["median"], 100.0)
        self.assertAlmostEqual(compute["all_samples"]["mad"], 2.0)
        self.assertAlmostEqual(compute["all_samples"]["relative_mad"], 0.02)
        self.assertAlmostEqual(
            compute["run_to_run"]["maximum_relative_deviation_from_median"],
            0.01,
        )
        self.assertNotIn("pass", report)
        self.assertNotIn("stable", report)

    def test_requires_three_captures(self) -> None:
        with self.assertRaises(RecordedRealError):
            baseline_quality_report(self.traces[:2], self.calibration)

    def test_rejects_device_mismatch(self) -> None:
        changed = copy.deepcopy(self.traces)
        changed[2]["device"]["memory_bus_width_bits"] = 256
        with self.assertRaises(RecordedRealError):
            baseline_quality_report(changed, self.calibration)


if __name__ == "__main__":
    unittest.main()
