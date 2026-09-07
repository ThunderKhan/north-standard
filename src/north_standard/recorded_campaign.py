"""Ground-truth-labelled evaluation for recorded accessible hardware (Mode R).

Ground truth and condition labels live only in the campaign manifest and output records.
They are never added to verifier-visible contract or evidence objects.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import statistics
from time import perf_counter_ns
from typing import Any

from .evaluation_protocol import wilson_interval
from .experiments import GroundTruth
from .models import Decision
from .policy import VerifierPolicy
from .recorded_protocol import validate_challenge_binding
from .recorded_real import (
    RECORDED_REAL,
    RecordedRealError,
    build_recorded_bundle,
    build_recorded_contract,
    load_json,
    load_traces,
)
from .verifier import verify

CAMPAIGN_SCHEMA_VERSION = "recorded-campaign/0.1"


@dataclass(frozen=True)
class RecordedTrialResult:
    campaign_id: str
    trial_id: str
    condition: str
    ground_truth: GroundTruth
    capture_ids: tuple[str, ...]
    contract_hash: str
    evidence_bundle_root: str
    verifier_policy_id: str
    decision: Decision
    reason_codes: tuple[str, ...]
    verifier_runtime_ns: int
    challenge_count: int
    min_normalized_score: float
    median_normalized_score: float
    median_compute_gflops: float
    median_memory_gbps: float
    median_challenge_runtime_ms: float
    total_challenge_runtime_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "recorded-verifier-trial/0.1",
            "campaign_id": self.campaign_id,
            "trial_id": self.trial_id,
            "condition": self.condition,
            "ground_truth": self.ground_truth.value,
            "capture_ids": list(self.capture_ids),
            "mode": RECORDED_REAL,
            "contract_hash": self.contract_hash,
            "evidence_bundle_root": self.evidence_bundle_root,
            "verifier_policy_id": self.verifier_policy_id,
            "decision": self.decision.value,
            "reason_codes": list(self.reason_codes),
            "verifier_runtime_ns": self.verifier_runtime_ns,
            "measurement": {
                "challenge_count": self.challenge_count,
                "min_normalized_score": self.min_normalized_score,
                "median_normalized_score": self.median_normalized_score,
                "median_compute_gflops": self.median_compute_gflops,
                "median_memory_gbps": self.median_memory_gbps,
                "median_challenge_runtime_ms": self.median_challenge_runtime_ms,
                "total_challenge_runtime_ms": self.total_challenge_runtime_ms,
            },
            "publication_ready": False,
        }


def validate_campaign_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != CAMPAIGN_SCHEMA_VERSION:
        raise RecordedRealError("unsupported recorded campaign schema_version")
    if manifest.get("mode") != RECORDED_REAL:
        raise RecordedRealError("recorded campaign mode must be RECORDED_REAL")
    campaign_id = manifest.get("campaign_id")
    if not isinstance(campaign_id, str) or not campaign_id:
        raise RecordedRealError("campaign_id is required")
    calibration_path = manifest.get("calibration_path")
    if not isinstance(calibration_path, str) or not calibration_path:
        raise RecordedRealError("calibration_path is required")
    floor = manifest.get("performance_floor")
    if isinstance(floor, bool) or not isinstance(floor, (int, float)) or float(floor) < 0:
        raise RecordedRealError("performance_floor must be numeric and >= 0")

    trials = manifest.get("trials")
    if not isinstance(trials, list) or len(trials) < 2:
        raise RecordedRealError("recorded campaign requires at least two trials")
    seen: set[str] = set()
    truths: set[GroundTruth] = set()
    for trial in trials:
        if not isinstance(trial, dict):
            raise RecordedRealError("each campaign trial must be an object")
        trial_id = trial.get("trial_id")
        condition = trial.get("condition")
        if not isinstance(trial_id, str) or not trial_id:
            raise RecordedRealError("trial_id is required")
        if trial_id in seen:
            raise RecordedRealError("trial_id values must be unique")
        seen.add(trial_id)
        if not isinstance(condition, str) or not condition:
            raise RecordedRealError("condition is required")
        try:
            truths.add(GroundTruth(trial.get("ground_truth")))
        except (TypeError, ValueError) as exc:
            raise RecordedRealError("ground_truth must be COMPLIANT or BREACH") from exc
        paths = trial.get("trace_paths")
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and p for p in paths):
            raise RecordedRealError("trace_paths must contain at least one path")

    if truths != {GroundTruth.COMPLIANT, GroundTruth.BREACH}:
        raise RecordedRealError(
            "campaign must contain at least one COMPLIANT and one BREACH trial"
        )


def _resolve(base_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


def _trial_measurements(traces: list[dict[str, Any]], bundle: Any) -> dict[str, float | int]:
    challenge_records = [
        record for record in bundle.records if record.evidence_type.value == "CHALLENGE"
    ]
    scores = [float(record.payload["score"]) for record in challenge_records]
    compute = [
        float(sample["compute_gflops"])
        for trace in traces
        for sample in trace["samples"]
    ]
    memory = [
        float(sample["memory_gbps"])
        for trace in traces
        for sample in trace["samples"]
    ]
    runtimes = [
        float(sample["compute_ms"]) + float(sample["memory_ms"])
        for trace in traces
        for sample in trace["samples"]
    ]
    if not scores or len(scores) != len(compute) or len(scores) != len(runtimes):
        raise RecordedRealError("recorded challenge measurement cardinality mismatch")
    return {
        "challenge_count": len(scores),
        "min_normalized_score": min(scores),
        "median_normalized_score": statistics.median(scores),
        "median_compute_gflops": statistics.median(compute),
        "median_memory_gbps": statistics.median(memory),
        "median_challenge_runtime_ms": statistics.median(runtimes),
        "total_challenge_runtime_ms": sum(runtimes),
    }


def run_campaign(
    manifest: dict[str, Any],
    *,
    base_dir: str | Path = ".",
) -> list[RecordedTrialResult]:
    validate_campaign_manifest(manifest)
    root = Path(base_dir)
    calibration = load_json(_resolve(root, manifest["calibration_path"]))
    rows: list[RecordedTrialResult] = []

    for trial in manifest["trials"]:
        traces = load_traces(_resolve(root, path) for path in trial["trace_paths"])
        validate_challenge_binding(calibration, traces)
        contract = build_recorded_contract(
            traces,
            performance_min_score=float(manifest["performance_floor"]),
        )
        bundle = build_recorded_bundle(contract, traces, calibration)
        measurements = _trial_measurements(traces, bundle)
        policy = VerifierPolicy(policy_id=contract.verifier_policy_id)
        started = perf_counter_ns()
        result = verify(contract, bundle, policy)
        elapsed = perf_counter_ns() - started
        rows.append(
            RecordedTrialResult(
                campaign_id=manifest["campaign_id"],
                trial_id=trial["trial_id"],
                condition=trial["condition"],
                ground_truth=GroundTruth(trial["ground_truth"]),
                capture_ids=tuple(str(trace["capture_id"]) for trace in traces),
                contract_hash=contract.semantic_hash,
                evidence_bundle_root=bundle.bundle_root,
                verifier_policy_id=policy.policy_id,
                decision=result.decision,
                reason_codes=result.reason_codes,
                verifier_runtime_ns=elapsed,
                challenge_count=int(measurements["challenge_count"]),
                min_normalized_score=float(measurements["min_normalized_score"]),
                median_normalized_score=float(measurements["median_normalized_score"]),
                median_compute_gflops=float(measurements["median_compute_gflops"]),
                median_memory_gbps=float(measurements["median_memory_gbps"]),
                median_challenge_runtime_ms=float(measurements["median_challenge_runtime_ms"]),
                total_challenge_runtime_ms=float(measurements["total_challenge_runtime_ms"]),
            )
        )
    return rows


def _interval(successes: int, total: int) -> dict[str, Any]:
    return wilson_interval(successes, total).to_dict()


def _measurement_summary(selected: list[RecordedTrialResult]) -> dict[str, Any]:
    return {
        "trials": len(selected),
        "total_challenges": sum(row.challenge_count for row in selected),
        "minimum_normalized_score": min(row.min_normalized_score for row in selected),
        "median_trial_normalized_score": statistics.median(
            row.median_normalized_score for row in selected
        ),
        "median_trial_compute_gflops": statistics.median(
            row.median_compute_gflops for row in selected
        ),
        "median_trial_memory_gbps": statistics.median(
            row.median_memory_gbps for row in selected
        ),
        "median_trial_challenge_runtime_ms": statistics.median(
            row.median_challenge_runtime_ms for row in selected
        ),
        "total_measured_challenge_runtime_ms": sum(
            row.total_challenge_runtime_ms for row in selected
        ),
    }


def campaign_summary(rows: list[RecordedTrialResult]) -> dict[str, Any]:
    if not rows:
        raise ValueError("recorded campaign rows must not be empty")
    compliant = [row for row in rows if row.ground_truth == GroundTruth.COMPLIANT]
    breaches = [row for row in rows if row.ground_truth == GroundTruth.BREACH]
    if not compliant or not breaches:
        raise ValueError("summary requires both compliant and breach trials")

    false_accepts = sum(row.decision == Decision.ACCEPT for row in breaches)
    false_rejects = sum(row.decision == Decision.REJECT for row in compliant)
    inconclusive = sum(row.decision == Decision.INCONCLUSIVE for row in rows)
    compliant_inconclusive = sum(row.decision == Decision.INCONCLUSIVE for row in compliant)
    breach_inconclusive = sum(row.decision == Decision.INCONCLUSIVE for row in breaches)

    per_condition: dict[str, Any] = {}
    for condition in sorted({row.condition for row in rows}):
        selected = [row for row in rows if row.condition == condition]
        counts = Counter(row.decision.value for row in selected)
        per_condition[condition] = {
            "trials": len(selected),
            "ground_truth_counts": dict(Counter(row.ground_truth.value for row in selected)),
            "decision_counts": dict(sorted(counts.items())),
            "measurement": _measurement_summary(selected),
        }

    return {
        "schema_version": "recorded-campaign-summary/0.1",
        "campaign_id": rows[0].campaign_id,
        "mode": RECORDED_REAL,
        "status": "RECORDED_ACCESSIBLE_HARDWARE_NOT_PRODUCTION_VALIDATION",
        "publication_ready": False,
        "total_trials": len(rows),
        "compliant_trials": len(compliant),
        "breach_trials": len(breaches),
        "far": _interval(false_accepts, len(breaches)),
        "frr": _interval(false_rejects, len(compliant)),
        "inconclusive_rate": _interval(inconclusive, len(rows)),
        "inconclusive_rate_compliant": _interval(compliant_inconclusive, len(compliant)),
        "inconclusive_rate_breach": _interval(breach_inconclusive, len(breaches)),
        "measurement": _measurement_summary(rows),
        "per_condition": per_condition,
        "notes": [
            "Ground-truth labels are campaign metadata and are never verifier inputs.",
            "Wilson intervals expose finite-sample uncertainty; zero observed error is not zero proven risk.",
            "Challenge runtime is measured as compute-kernel time plus memory-kernel time; host orchestration and evidence serialization are reported separately by verifier_runtime_ns.",
            "Compute GFLOP/s and memory GB/s are custom research-probe measurements, not standardized benchmark scores.",
            "Mode R measures the accessible device only and does not validate H100-class or remote-provider claims.",
        ],
    }


def write_campaign_results(
    rows: list[RecordedTrialResult], output_dir: str | Path
) -> tuple[Path, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    raw_path = target / "recorded_trials.jsonl"
    summary_path = target / "recorded_summary.json"
    with raw_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row.to_dict(), sort_keys=True, separators=(",", ":")))
            handle.write("\n")
    summary_path.write_text(
        json.dumps(campaign_summary(rows), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return raw_path, summary_path
