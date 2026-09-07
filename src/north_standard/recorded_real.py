"""Recorded-accessible-hardware (Mode R) ingestion and replay.

The CUDA collector produces local software-recorded traces. These traces are physical
measurements, but they are *not* hardware-rooted attestation and they must never be
presented as H100 evidence or as production-calibrated SLA truth.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterable, Sequence

from .canonical import canonical_sha256
from .models import ComputeContract, EvidenceBundle, EvidenceRecord, EvidenceType

TRACE_SCHEMA_VERSION = "gpu-trace/0.1"
CALIBRATION_SCHEMA_VERSION = "gpu-calibration/0.1"
RECORDED_REAL = "RECORDED_REAL"
CALIBRATION_STATUS = "RESEARCH_CALIBRATION_NOT_PRODUCTION_THRESHOLD"

_DEVICE_FINGERPRINT_FIELDS = (
    "name",
    "compute_capability_major",
    "compute_capability_minor",
    "global_memory_bytes",
    "multiprocessor_count",
    "memory_bus_width_bits",
)


class RecordedRealError(ValueError):
    """Raised when a trace cannot safely enter the Mode R pipeline."""


def _positive_finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecordedRealError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise RecordedRealError(f"{field} must be finite and > 0")
    return result


def _required_string(mapping: dict[str, Any], field: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value:
        raise RecordedRealError(f"{field} must be a non-empty string")
    return value


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise RecordedRealError(f"{path} must contain a JSON object")
    return value


def save_json(path: str | Path, value: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def validate_trace(trace: dict[str, Any]) -> None:
    if trace.get("schema_version") != TRACE_SCHEMA_VERSION:
        raise RecordedRealError("unsupported gpu trace schema_version")
    if trace.get("provenance") != RECORDED_REAL:
        raise RecordedRealError("Mode R accepts only provenance=RECORDED_REAL")

    for field in (
        "capture_id",
        "contract_id",
        "session_id",
        "runtime_profile_id",
        "benchmark_profile_id",
    ):
        _required_string(trace, field)

    captured_at = trace.get("captured_at_unix_ms")
    if isinstance(captured_at, bool) or not isinstance(captured_at, int) or captured_at < 0:
        raise RecordedRealError("captured_at_unix_ms must be a non-negative integer")

    collector = trace.get("collector")
    if not isinstance(collector, dict):
        raise RecordedRealError("collector must be an object")
    if collector.get("name") != "north-standard-cuda-probe":
        raise RecordedRealError("unsupported collector")
    if collector.get("authentication") != "LOCAL_SOFTWARE_ONLY":
        raise RecordedRealError("Mode R v0.1 expects LOCAL_SOFTWARE_ONLY authentication")

    device = trace.get("device")
    if not isinstance(device, dict):
        raise RecordedRealError("device must be an object")
    for field in _DEVICE_FINGERPRINT_FIELDS:
        if field not in device:
            raise RecordedRealError(f"device.{field} is required")
    _required_string(device, "name")
    for field in _DEVICE_FINGERPRINT_FIELDS[1:]:
        value = device.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RecordedRealError(f"device.{field} must be a positive integer")

    challenge = trace.get("challenge")
    if not isinstance(challenge, dict):
        raise RecordedRealError("challenge must be an object")
    for field in ("elements", "compute_inner_iterations", "measurement_iterations"):
        value = challenge.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RecordedRealError(f"challenge.{field} must be a positive integer")
    if challenge["measurement_iterations"] < 2:
        raise RecordedRealError("challenge.measurement_iterations must be >= 2")

    samples = trace.get("samples")
    if not isinstance(samples, list) or len(samples) < 2:
        raise RecordedRealError("at least two recorded samples are required")
    if challenge["measurement_iterations"] != len(samples):
        raise RecordedRealError("measurement_iterations must equal the number of samples")

    seen_indices: set[int] = set()
    previous_observed = -1
    for sample in samples:
        if not isinstance(sample, dict):
            raise RecordedRealError("each sample must be an object")
        index = sample.get("sample_index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise RecordedRealError("sample_index must be a non-negative integer")
        if index in seen_indices:
            raise RecordedRealError("sample_index values must be unique")
        seen_indices.add(index)

        observed = sample.get("observed_at_unix_ms")
        if isinstance(observed, bool) or not isinstance(observed, int) or observed < 0:
            raise RecordedRealError("sample observed_at_unix_ms must be non-negative")
        if observed < previous_observed:
            raise RecordedRealError("sample timestamps must be monotonic")
        previous_observed = observed

        for field in ("compute_ms", "compute_gflops", "memory_ms", "memory_gbps"):
            _positive_finite(sample.get(field), f"sample.{field}")


def device_fingerprint(trace: dict[str, Any]) -> str:
    validate_trace(trace)
    device = trace["device"]
    identity = {field: device[field] for field in _DEVICE_FINGERPRINT_FIELDS}
    return canonical_sha256(identity)


def _compatible_trace_key(trace: dict[str, Any]) -> tuple[str, str, str]:
    return (
        device_fingerprint(trace),
        str(trace["runtime_profile_id"]),
        str(trace["benchmark_profile_id"]),
    )


def build_calibration(
    traces: Sequence[dict[str, Any]],
    *,
    calibration_id: str,
    created_at_unix_ms: int | None = None,
) -> dict[str, Any]:
    if not traces:
        raise RecordedRealError("at least one healthy recorded trace is required")
    if not calibration_id:
        raise RecordedRealError("calibration_id is required")

    for trace in traces:
        validate_trace(trace)

    expected_key = _compatible_trace_key(traces[0])
    if any(_compatible_trace_key(trace) != expected_key for trace in traces[1:]):
        raise RecordedRealError(
            "all calibration traces must share device, runtime profile, and benchmark profile"
        )

    compute_values = [
        _positive_finite(sample["compute_gflops"], "sample.compute_gflops")
        for trace in traces
        for sample in trace["samples"]
    ]
    memory_values = [
        _positive_finite(sample["memory_gbps"], "sample.memory_gbps")
        for trace in traces
        for sample in trace["samples"]
    ]

    source_ids = [str(trace["capture_id"]) for trace in traces]
    if len(set(source_ids)) != len(source_ids):
        raise RecordedRealError("calibration capture_id values must be unique")

    if created_at_unix_ms is None:
        created_at_unix_ms = max(int(trace["captured_at_unix_ms"]) for trace in traces)

    return {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "provenance": RECORDED_REAL,
        "calibration_id": calibration_id,
        "created_at_unix_ms": int(created_at_unix_ms),
        "device_fingerprint": expected_key[0],
        "device": dict(traces[0]["device"]),
        "runtime_profile_id": expected_key[1],
        "benchmark_profile_id": expected_key[2],
        "reference_compute_gflops": statistics.median(compute_values),
        "reference_memory_gbps": statistics.median(memory_values),
        "trace_count": len(traces),
        "sample_count": len(compute_values),
        "source_capture_ids": source_ids,
        "status": CALIBRATION_STATUS,
        "limitations": [
            "Calibration is device/profile specific and must not be generalized to other GPU classes.",
            "Reference values are medians of explicitly designated healthy recorded captures.",
            "The resulting normalized score is a research metric, not a production SLA standard.",
        ],
    }


def validate_calibration(calibration: dict[str, Any]) -> None:
    if calibration.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
        raise RecordedRealError("unsupported gpu calibration schema_version")
    if calibration.get("provenance") != RECORDED_REAL:
        raise RecordedRealError("calibration provenance must be RECORDED_REAL")
    if calibration.get("status") != CALIBRATION_STATUS:
        raise RecordedRealError("unsupported calibration status")
    _required_string(calibration, "calibration_id")
    fingerprint = _required_string(calibration, "device_fingerprint")
    if len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint):
        raise RecordedRealError("device_fingerprint must be lowercase SHA-256 hex")
    _required_string(calibration, "runtime_profile_id")
    _required_string(calibration, "benchmark_profile_id")
    _positive_finite(calibration.get("reference_compute_gflops"), "reference_compute_gflops")
    _positive_finite(calibration.get("reference_memory_gbps"), "reference_memory_gbps")


def score_sample(sample: dict[str, Any], calibration: dict[str, Any]) -> dict[str, float]:
    validate_calibration(calibration)
    compute = _positive_finite(sample.get("compute_gflops"), "sample.compute_gflops")
    memory = _positive_finite(sample.get("memory_gbps"), "sample.memory_gbps")
    compute_ratio = compute / float(calibration["reference_compute_gflops"])
    memory_ratio = memory / float(calibration["reference_memory_gbps"])

    # A bottleneck-sensitive composite: either primitive can lower the service score.
    # This is intentionally simple and experiment-defined so its behavior can be ablated.
    score = min(compute_ratio, memory_ratio)
    return {
        "score": score,
        "compute_ratio": compute_ratio,
        "memory_ratio": memory_ratio,
    }


def _ensure_trace_matches_calibration(
    trace: dict[str, Any], calibration: dict[str, Any]
) -> None:
    validate_trace(trace)
    validate_calibration(calibration)
    if device_fingerprint(trace) != calibration["device_fingerprint"]:
        raise RecordedRealError("trace device does not match calibration device")
    if trace["runtime_profile_id"] != calibration["runtime_profile_id"]:
        raise RecordedRealError("trace runtime profile does not match calibration")
    if trace["benchmark_profile_id"] != calibration["benchmark_profile_id"]:
        raise RecordedRealError("trace benchmark profile does not match calibration")


def build_recorded_contract(
    traces: Sequence[dict[str, Any]],
    *,
    performance_min_score: float = 0.80,
    provider_id: str = "provider-local-recording",
    buyer_id: str = "buyer-local-recording",
    verifier_policy_id: str = "VERIFIER-v0.1",
    settlement_policy_id: str = "SETTLEMENT-v0.1",
) -> ComputeContract:
    if not traces:
        raise RecordedRealError("at least one trace is required")
    for trace in traces:
        validate_trace(trace)

    contract_ids = {str(trace["contract_id"]) for trace in traces}
    session_ids = {str(trace["session_id"]) for trace in traces}
    runtime_profiles = {str(trace["runtime_profile_id"]) for trace in traces}
    benchmark_profiles = {str(trace["benchmark_profile_id"]) for trace in traces}
    fingerprints = {device_fingerprint(trace) for trace in traces}
    if any(len(values) != 1 for values in (contract_ids, session_ids, runtime_profiles, benchmark_profiles, fingerprints)):
        raise RecordedRealError("recorded replay traces must share contract/session/device/profile")

    observed_seconds = [
        int(sample["observed_at_unix_ms"]) // 1000
        for trace in traces
        for sample in trace["samples"]
    ]
    delivery_start = min(observed_seconds)
    duration_seconds = max(60, max(observed_seconds) - delivery_start + 1)

    return ComputeContract(
        schema_version="compute-contract/0.1",
        contract_id=next(iter(contract_ids)),
        contract_class_id="RECORDED-ACCESSIBLE-GPU-v0.1",
        provider_id=provider_id,
        buyer_id=buyer_id,
        session_id=next(iter(session_ids)),
        runtime_profile_id=next(iter(runtime_profiles)),
        delivery_start=delivery_start,
        duration_seconds=duration_seconds,
        sla_policy_id="SLA-RECORDED-RESEARCH-v0.1",
        benchmark_profile_id=next(iter(benchmark_profiles)),
        performance_min_score=float(performance_min_score),
        verifier_policy_id=verifier_policy_id,
        settlement_policy_id=settlement_policy_id,
        research_mode=True,
    )


def build_recorded_bundle(
    contract: ComputeContract,
    traces: Sequence[dict[str, Any]],
    calibration: dict[str, Any],
    *,
    producer_id: str = "north-standard-recorded-harness",
) -> EvidenceBundle:
    if not traces:
        raise RecordedRealError("at least one recorded trace is required")
    validate_calibration(calibration)
    for trace in traces:
        _ensure_trace_matches_calibration(trace, calibration)
        if trace["contract_id"] != contract.contract_id or trace["session_id"] != contract.session_id:
            raise RecordedRealError("trace contract/session does not match replay contract")

    first_trace = traces[0]
    first_observed = int(first_trace["samples"][0]["observed_at_unix_ms"]) // 1000
    sequence = 1
    records: list[EvidenceRecord] = []

    common_provenance = {
        "provenance": RECORDED_REAL,
        "collector": "north-standard-cuda-probe/0.1",
        "collector_authentication": "LOCAL_SOFTWARE_ONLY",
        "device_fingerprint": calibration["device_fingerprint"],
        "calibration_id": calibration["calibration_id"],
    }

    def append_record(
        evidence_id: str,
        evidence_type: EvidenceType,
        observed_at: int,
        payload: dict[str, Any],
    ) -> None:
        nonlocal sequence
        records.append(
            EvidenceRecord(
                schema_version="evidence/0.1",
                evidence_id=evidence_id,
                evidence_type=evidence_type,
                producer_id=producer_id,
                contract_id=contract.contract_id,
                session_id=contract.session_id,
                observed_at=observed_at,
                received_at=observed_at,
                sequence_number=sequence,
                payload={**common_provenance, **payload},
                nonce=f"recorded:{contract.contract_id}:{contract.session_id}:{sequence}:{evidence_id}",
                authentication_valid=True,
                trust_tier="T0",
            )
        )
        sequence += 1

    append_record(
        "recorded-binding",
        EvidenceType.SESSION_BINDING,
        first_observed,
        {
            "bound": True,
            "binding_method": "LOCAL_CAPTURE_ARGUMENTS",
            "trust_statement": "No hardware-rooted session attestation is claimed.",
        },
    )
    append_record(
        "recorded-runtime",
        EvidenceType.RUNTIME_CHECK,
        first_observed,
        {
            "usable": True,
            "runtime_profile_id": contract.runtime_profile_id,
            "cuda_runtime_version": first_trace["device"].get("cuda_runtime_version"),
            "cuda_driver_version": first_trace["device"].get("cuda_driver_version"),
        },
    )
    append_record(
        "recorded-telemetry",
        EvidenceType.TELEMETRY,
        first_observed,
        {
            "service_state": "HEALTHY",
            "telemetry_scope": "CUDA_PROBE_COMPLETED",
        },
    )

    for trace in traces:
        for sample in trace["samples"]:
            observed_at = int(sample["observed_at_unix_ms"]) // 1000
            normalized = score_sample(sample, calibration)
            append_record(
                f"recorded-challenge-{trace['capture_id']}-{sample['sample_index']}",
                EvidenceType.CHALLENGE,
                observed_at,
                {
                    "score": normalized["score"],
                    "timed_out": False,
                    "score_method": "MIN_COMPUTE_MEMORY_RATIO_v0.1",
                    "threshold_status": "EXPERIMENT_DEFINED",
                    "capture_id": trace["capture_id"],
                    "sample_index": sample["sample_index"],
                    "compute_gflops": sample["compute_gflops"],
                    "memory_gbps": sample["memory_gbps"],
                    "compute_ratio": normalized["compute_ratio"],
                    "memory_ratio": normalized["memory_ratio"],
                },
            )

    return EvidenceBundle(
        contract_id=contract.contract_id,
        session_id=contract.session_id,
        records=tuple(records),
    )


def load_traces(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    traces = [load_json(path) for path in paths]
    for trace in traces:
        validate_trace(trace)
    return traces
