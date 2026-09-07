from __future__ import annotations

import copy
import unittest

from north_standard.models import Decision
from north_standard.policy import VerifierPolicy
from north_standard.recorded_real import (
    RECORDED_REAL,
    RecordedRealError,
    build_calibration,
    build_recorded_bundle,
    build_recorded_contract,
    device_fingerprint,
    score_sample,
    validate_trace,
)
from north_standard.verifier import verify


def make_trace(
    capture_id: str,
    *,
    compute: tuple[float, ...] = (100.0, 102.0, 98.0),
    memory: tuple[float, ...] = (200.0, 204.0, 196.0),
    captured_at_ms: int = 1_800_000_000_000,
) -> dict:
    samples = []
    for index, (compute_value, memory_value) in enumerate(zip(compute, memory, strict=True)):
        samples.append(
            {
                "sample_index": index,
                "observed_at_unix_ms": captured_at_ms + index * 1000,
                "compute_ms": 1.0,
                "compute_gflops": compute_value,
                "memory_ms": 1.0,
                "memory_gbps": memory_value,
            }
        )
    return {
        "schema_version": "gpu-trace/0.1",
        "provenance": RECORDED_REAL,
        "capture_id": capture_id,
        "captured_at_unix_ms": captured_at_ms,
        "contract_id": "recorded-contract-001",
        "session_id": "recorded-session-001",
        "runtime_profile_id": "CUDA-RECORDED-v0.1",
        "benchmark_profile_id": "CUDA-MICROBENCH-v0.1",
        "collector": {
            "name": "north-standard-cuda-probe",
            "version": "0.1",
            "authentication": "LOCAL_SOFTWARE_ONLY",
        },
        "device": {
            "ordinal": 0,
            "name": "TEST GPU - NOT A REAL MEASUREMENT",
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
        "limitations": ["Unit-test fixture only; this object is not empirical evidence."],
    }


class RecordedRealTests(unittest.TestCase):
    def test_trace_requires_recorded_real_provenance(self) -> None:
        trace = make_trace("healthy-a")
        trace["provenance"] = "SYNTHETIC"
        with self.assertRaises(RecordedRealError):
            validate_trace(trace)

    def test_device_fingerprint_ignores_driver_version_but_binds_hardware_shape(self) -> None:
        trace = make_trace("healthy-a")
        changed_driver = copy.deepcopy(trace)
        changed_driver["device"]["cuda_driver_version"] += 1
        self.assertEqual(device_fingerprint(trace), device_fingerprint(changed_driver))

        different_bus = copy.deepcopy(trace)
        different_bus["device"]["memory_bus_width_bits"] = 256
        self.assertNotEqual(device_fingerprint(trace), device_fingerprint(different_bus))

    def test_calibration_uses_medians_of_designated_healthy_captures(self) -> None:
        first = make_trace("healthy-a", compute=(90.0, 100.0, 110.0), memory=(180.0, 200.0, 220.0))
        second = make_trace("healthy-b", compute=(95.0, 105.0, 115.0), memory=(190.0, 210.0, 230.0))
        calibration = build_calibration(
            [first, second],
            calibration_id="rtx3050-healthy-v0.1",
        )
        self.assertEqual(calibration["reference_compute_gflops"], 102.5)
        self.assertEqual(calibration["reference_memory_gbps"], 205.0)
        self.assertEqual(calibration["sample_count"], 6)
        self.assertFalse("production" in calibration["calibration_id"].lower())

    def test_calibration_rejects_mixed_devices(self) -> None:
        first = make_trace("healthy-a")
        second = make_trace("healthy-b")
        second["device"]["memory_bus_width_bits"] = 256
        with self.assertRaises(RecordedRealError):
            build_calibration([first, second], calibration_id="bad-mixed-device")

    def test_score_is_bottleneck_sensitive_minimum_ratio(self) -> None:
        healthy = make_trace("healthy-a", compute=(100.0, 100.0), memory=(200.0, 200.0))
        calibration = build_calibration([healthy], calibration_id="healthy")
        score = score_sample(
            {
                "compute_gflops": 90.0,
                "memory_gbps": 100.0,
            },
            calibration,
        )
        self.assertAlmostEqual(score["compute_ratio"], 0.9)
        self.assertAlmostEqual(score["memory_ratio"], 0.5)
        self.assertAlmostEqual(score["score"], 0.5)

    def test_same_device_recorded_replay_accepts_against_its_healthy_baseline(self) -> None:
        baseline = make_trace("healthy-baseline", compute=(100.0, 100.0, 100.0), memory=(200.0, 200.0, 200.0))
        evaluation = make_trace("healthy-eval", compute=(98.0, 101.0, 99.0), memory=(196.0, 202.0, 198.0), captured_at_ms=1_800_000_010_000)
        calibration = build_calibration([baseline], calibration_id="healthy")
        contract = build_recorded_contract([evaluation], performance_min_score=0.80)
        bundle = build_recorded_bundle(contract, [evaluation], calibration)
        result = verify(contract, bundle, VerifierPolicy(policy_id=contract.verifier_policy_id))

        self.assertEqual(result.decision, Decision.ACCEPT)
        challenge_records = [record for record in bundle.records if record.evidence_type.value == "CHALLENGE"]
        self.assertTrue(challenge_records)
        self.assertTrue(all(record.payload["provenance"] == RECORDED_REAL for record in challenge_records))
        self.assertTrue(all(record.trust_tier == "T0" for record in bundle.records))

    def test_recorded_degradation_rejects_when_multiple_samples_cross_experimental_floor(self) -> None:
        baseline = make_trace("healthy-baseline", compute=(100.0, 100.0, 100.0), memory=(200.0, 200.0, 200.0))
        degraded = make_trace("degraded", compute=(50.0, 55.0, 52.0), memory=(105.0, 100.0, 110.0), captured_at_ms=1_800_000_020_000)
        calibration = build_calibration([baseline], calibration_id="healthy")
        contract = build_recorded_contract([degraded], performance_min_score=0.80)
        bundle = build_recorded_bundle(contract, [degraded], calibration)
        result = verify(contract, bundle, VerifierPolicy(policy_id=contract.verifier_policy_id))
        self.assertEqual(result.decision, Decision.REJECT)
        self.assertIn("CHALLENGE_PERFORMANCE_BREACH", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
