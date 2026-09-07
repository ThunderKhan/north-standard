from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from north_standard.models import Decision
from north_standard.recorded_campaign import campaign_summary, run_campaign
from north_standard.recorded_protocol import (
    bind_calibration_to_challenge,
    challenge_fingerprint,
    validate_challenge_binding,
)
from north_standard.recorded_real import RecordedRealError, build_calibration, save_json


def trace(
    capture_id: str,
    *,
    contract_id: str,
    session_id: str,
    compute: float,
    memory: float,
    captured_at_ms: int,
) -> dict:
    samples = [
        {
            "sample_index": index,
            "observed_at_unix_ms": captured_at_ms + index * 1000,
            "compute_ms": 1.0,
            "compute_gflops": compute,
            "memory_ms": 1.0,
            "memory_gbps": memory,
        }
        for index in range(3)
    ]
    return {
        "schema_version": "gpu-trace/0.1",
        "provenance": "RECORDED_REAL",
        "capture_id": capture_id,
        "captured_at_unix_ms": captured_at_ms,
        "contract_id": contract_id,
        "session_id": session_id,
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
            "measurement_iterations": 3,
        },
        "samples": samples,
        "limitations": ["Unit-test fixture; not a physical measurement."],
    }


class RecordedProtocolTests(unittest.TestCase):
    def test_calibration_binds_exact_challenge_shape(self) -> None:
        baseline = trace(
            "baseline",
            contract_id="baseline-contract",
            session_id="baseline-session",
            compute=100.0,
            memory=200.0,
            captured_at_ms=1_800_000_000_000,
        )
        calibration = bind_calibration_to_challenge(
            build_calibration([baseline], calibration_id="cal"),
            [baseline],
        )
        self.assertEqual(calibration["challenge_fingerprint"], challenge_fingerprint(baseline))
        validate_challenge_binding(calibration, [baseline])

        changed = copy.deepcopy(baseline)
        changed["challenge"]["compute_inner_iterations"] = 64
        with self.assertRaises(RecordedRealError):
            validate_challenge_binding(calibration, [changed])

    def test_campaign_keeps_ground_truth_outside_verifier_inputs_and_measures_errors(self) -> None:
        baseline = trace(
            "baseline",
            contract_id="baseline-contract",
            session_id="baseline-session",
            compute=100.0,
            memory=200.0,
            captured_at_ms=1_800_000_000_000,
        )
        healthy = trace(
            "healthy",
            contract_id="trial-healthy",
            session_id="session-healthy",
            compute=98.0,
            memory=196.0,
            captured_at_ms=1_800_000_010_000,
        )
        degraded = trace(
            "degraded",
            contract_id="trial-degraded",
            session_id="session-degraded",
            compute=50.0,
            memory=100.0,
            captured_at_ms=1_800_000_020_000,
        )
        calibration = bind_calibration_to_challenge(
            build_calibration([baseline], calibration_id="cal"),
            [baseline],
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_json(root / "calibration.json", calibration)
            save_json(root / "healthy.json", healthy)
            save_json(root / "degraded.json", degraded)
            manifest = {
                "schema_version": "recorded-campaign/0.1",
                "campaign_id": "test-recorded-campaign",
                "mode": "RECORDED_REAL",
                "calibration_path": "calibration.json",
                "performance_floor": 0.80,
                "trials": [
                    {
                        "trial_id": "healthy-01",
                        "condition": "healthy_idle",
                        "ground_truth": "COMPLIANT",
                        "trace_paths": ["healthy.json"],
                    },
                    {
                        "trial_id": "degraded-01",
                        "condition": "gpu_contention",
                        "ground_truth": "BREACH",
                        "trace_paths": ["degraded.json"],
                    },
                ],
            }
            rows = run_campaign(manifest, base_dir=root)

        self.assertEqual([row.decision for row in rows], [Decision.ACCEPT, Decision.REJECT])
        self.assertEqual(rows[0].challenge_count, 3)
        self.assertAlmostEqual(rows[0].median_normalized_score, 0.98)
        self.assertAlmostEqual(rows[1].median_normalized_score, 0.50)
        self.assertAlmostEqual(rows[0].median_challenge_runtime_ms, 2.0)
        self.assertAlmostEqual(rows[0].total_challenge_runtime_ms, 6.0)

        summary = campaign_summary(rows)
        self.assertEqual(summary["far"]["numerator"], 0)
        self.assertEqual(summary["frr"]["numerator"], 0)
        self.assertGreater(summary["far"]["upper"], 0.0)
        self.assertGreater(summary["frr"]["upper"], 0.0)
        self.assertEqual(summary["measurement"]["total_challenges"], 6)
        self.assertAlmostEqual(
            summary["per_condition"]["gpu_contention"]["measurement"]["median_trial_normalized_score"],
            0.50,
        )
        serialized = json.dumps([row.to_dict() for row in rows])
        self.assertIn("ground_truth", serialized)
        self.assertNotIn("ground_truth", json.dumps(healthy))


if __name__ == "__main__":
    unittest.main()
