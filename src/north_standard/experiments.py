"""Seeded synthetic experiment harness for adversarial verifier evaluation.

Ground truth is experiment metadata only. It is never inserted into the compute contract,
evidence bundle, verifier policy, or verifier call. This keeps evaluation labels outside
the system being evaluated.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from enum import Enum
import json
from pathlib import Path
from random import Random
from time import perf_counter_ns
from typing import Any

from .models import Decision, EvidenceBundle, EvidenceType
from .simulator import Scenario, simulate_scenario
from .verifier import verify


class GroundTruth(str, Enum):
    COMPLIANT = "COMPLIANT"
    BREACH = "BREACH"


class SyntheticCase(str, Enum):
    HEALTHY_VARIANCE = "healthy_variance"
    MARGINAL_HEALTHY = "marginal_healthy"
    MILD_THROTTLE = "mild_throttle"
    SEVERE_THROTTLE = "severe_throttle"
    REPLAYED_EVIDENCE = "replayed_evidence"
    BUYER_NETWORK_FAILURE = "buyer_network_failure"
    PROVIDER_OUTAGE = "provider_outage"
    TELEMETRY_GAP = "telemetry_gap"


@dataclass(frozen=True)
class CaseSpec:
    ground_truth: GroundTruth
    attack_family: str
    hidden_performance_mean: float | None = None
    measurement_spread: float = 0.0


CASE_SPECS: dict[SyntheticCase, CaseSpec] = {
    SyntheticCase.HEALTHY_VARIANCE: CaseSpec(
        GroundTruth.COMPLIANT, "healthy-control", 0.96, 0.08
    ),
    # Hidden service mean remains above the experiment-defined 0.80 floor; challenge
    # observations are deliberately noisy to exercise false-reject/abstention behavior.
    SyntheticCase.MARGINAL_HEALTHY: CaseSpec(
        GroundTruth.COMPLIANT, "measurement-noise", 0.83, 0.07
    ),
    SyntheticCase.MILD_THROTTLE: CaseSpec(
        GroundTruth.BREACH, "performance-throttle", 0.76, 0.08
    ),
    SyntheticCase.SEVERE_THROTTLE: CaseSpec(
        GroundTruth.BREACH, "performance-throttle", 0.60, 0.07
    ),
    SyntheticCase.REPLAYED_EVIDENCE: CaseSpec(
        GroundTruth.BREACH, "binding-replay"
    ),
    SyntheticCase.BUYER_NETWORK_FAILURE: CaseSpec(
        GroundTruth.COMPLIANT, "buyer-network-fault"
    ),
    SyntheticCase.PROVIDER_OUTAGE: CaseSpec(
        GroundTruth.BREACH, "availability-outage"
    ),
    SyntheticCase.TELEMETRY_GAP: CaseSpec(
        GroundTruth.COMPLIANT, "evidence-missingness"
    ),
}


@dataclass(frozen=True)
class TrialRecord:
    experiment_id: str
    scenario: str
    attack_family: str
    ground_truth: GroundTruth
    seed: int
    mode: str
    contract_hash: str
    evidence_bundle_root: str
    verifier_policy_id: str
    decision: Decision
    reason_codes: tuple[str, ...]
    verifier_runtime_ns: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "verifier-trial/0.1",
            "experiment_id": self.experiment_id,
            "scenario": self.scenario,
            "attack_family": self.attack_family,
            "ground_truth": self.ground_truth.value,
            "seed": self.seed,
            "mode": self.mode,
            "contract_hash": self.contract_hash,
            "evidence_bundle_root": self.evidence_bundle_root,
            "verifier_policy_id": self.verifier_policy_id,
            "decision": self.decision.value,
            "reason_codes": list(self.reason_codes),
            "verifier_runtime_ns": self.verifier_runtime_ns,
            "publication_ready": False,
        }


def _performance_bundle(case: SyntheticCase, seed: int) -> tuple[Any, EvidenceBundle]:
    spec = CASE_SPECS[case]
    if spec.hidden_performance_mean is None:
        raise ValueError(f"{case.value} is not a performance case")

    contract, bundle = simulate_scenario(Scenario.HEALTHY_SERVICE)
    rng = Random(seed)
    records = []
    for record in bundle.records:
        if record.evidence_type != EvidenceType.CHALLENGE:
            records.append(record)
            continue
        jitter = (rng.random() * 2.0 - 1.0) * spec.measurement_spread
        score = max(0.0, min(1.20, spec.hidden_performance_mean + jitter))
        records.append(
            replace(
                record,
                payload={**record.payload, "score": round(score, 6), "timed_out": False},
            )
        )
    return contract, replace(bundle, records=tuple(records))


def generate_case_evidence(case: SyntheticCase | str, seed: int) -> tuple[Any, EvidenceBundle]:
    """Generate verifier-visible evidence without exposing ground truth to the verifier."""

    case = SyntheticCase(case)
    if seed < 0:
        raise ValueError("seed must be non-negative")

    if CASE_SPECS[case].hidden_performance_mean is not None:
        return _performance_bundle(case, seed)

    if case == SyntheticCase.REPLAYED_EVIDENCE:
        return simulate_scenario(Scenario.REPLAYED_EVIDENCE)

    if case == SyntheticCase.BUYER_NETWORK_FAILURE:
        return simulate_scenario(Scenario.AMBIGUOUS_NETWORK_FAILURE)

    contract, bundle = simulate_scenario(Scenario.HEALTHY_SERVICE)

    if case == SyntheticCase.PROVIDER_OUTAGE:
        records = []
        for record in bundle.records:
            if record.evidence_type == EvidenceType.TELEMETRY:
                records.append(replace(record, payload={"service_state": "UNAVAILABLE"}))
            elif record.evidence_type == EvidenceType.EXTERNAL_PROBE:
                records.append(
                    replace(record, payload={"result": "FAILURE", "attribution": "PROVIDER"})
                )
            elif record.evidence_type == EvidenceType.CHALLENGE:
                records.append(
                    replace(
                        record,
                        payload={
                            **record.payload,
                            "timed_out": True,
                            "timeout_attribution": "PROVIDER",
                        },
                    )
                )
            else:
                records.append(record)
        return contract, replace(bundle, records=tuple(records))

    if case == SyntheticCase.TELEMETRY_GAP:
        records = tuple(
            record for record in bundle.records if record.evidence_type != EvidenceType.TELEMETRY
        )
        return contract, replace(bundle, records=records)

    raise AssertionError(f"unhandled synthetic case: {case.value}")


def run_trial(case: SyntheticCase | str, seed: int) -> TrialRecord:
    case = SyntheticCase(case)
    spec = CASE_SPECS[case]
    contract, bundle = generate_case_evidence(case, seed)

    start_ns = perf_counter_ns()
    result = verify(contract, bundle)
    runtime_ns = perf_counter_ns() - start_ns

    return TrialRecord(
        experiment_id="synthetic-smoke/0.1",
        scenario=case.value,
        attack_family=spec.attack_family,
        ground_truth=spec.ground_truth,
        seed=seed,
        mode="SYNTHETIC",
        contract_hash=contract.semantic_hash,
        evidence_bundle_root=bundle.bundle_root,
        verifier_policy_id=result.verifier_policy_id,
        decision=result.decision,
        reason_codes=tuple(result.reason_codes),
        verifier_runtime_ns=runtime_ns,
    )


def run_matrix(*, trials_per_scenario: int, base_seed: int) -> list[TrialRecord]:
    if trials_per_scenario < 1:
        raise ValueError("trials_per_scenario must be >= 1")
    if base_seed < 0:
        raise ValueError("base_seed must be non-negative")

    trials: list[TrialRecord] = []
    for scenario_index, case in enumerate(SyntheticCase):
        seed_base = base_seed + scenario_index * 1_000_003
        for trial_index in range(trials_per_scenario):
            trials.append(run_trial(case, seed_base + trial_index))
    return trials


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def summarize(trials: list[TrialRecord]) -> dict[str, Any]:
    total = len(trials)
    compliant = [trial for trial in trials if trial.ground_truth == GroundTruth.COMPLIANT]
    breaches = [trial for trial in trials if trial.ground_truth == GroundTruth.BREACH]
    false_accepts = [trial for trial in breaches if trial.decision == Decision.ACCEPT]
    false_rejects = [trial for trial in compliant if trial.decision == Decision.REJECT]
    inconclusive = [trial for trial in trials if trial.decision == Decision.INCONCLUSIVE]
    compliant_inconclusive = [
        trial for trial in compliant if trial.decision == Decision.INCONCLUSIVE
    ]
    breach_inconclusive = [
        trial for trial in breaches if trial.decision == Decision.INCONCLUSIVE
    ]

    decisions = Counter(trial.decision.value for trial in trials)
    per_scenario: dict[str, dict[str, int]] = {}
    for case in SyntheticCase:
        rows = [trial for trial in trials if trial.scenario == case.value]
        per_scenario[case.value] = dict(Counter(trial.decision.value for trial in rows))

    return {
        "schema_version": "experiment-summary/0.1",
        "experiment_id": "synthetic-smoke/0.1",
        "mode": "SYNTHETIC",
        "publication_ready": False,
        "status": "SMOKE_ONLY_NOT_PUBLICATION_READY",
        "total_trials": total,
        "compliant_trials": len(compliant),
        "breach_trials": len(breaches),
        "false_accepts": len(false_accepts),
        "false_rejects": len(false_rejects),
        "inconclusive_trials": len(inconclusive),
        "far": _rate(len(false_accepts), len(breaches)),
        "frr": _rate(len(false_rejects), len(compliant)),
        "inconclusive_rate": _rate(len(inconclusive), total),
        "inconclusive_rate_compliant": _rate(len(compliant_inconclusive), len(compliant)),
        "inconclusive_rate_breach": _rate(len(breach_inconclusive), len(breaches)),
        "decision_counts": dict(decisions),
        "per_scenario_decision_counts": per_scenario,
        "notes": [
            "Synthetic smoke metrics validate the experiment pipeline; they are not publication claims.",
            "No confidence intervals, held-out suite, baselines, or real-hardware provenance are included yet.",
            "The current performance floor and synthetic observation distributions are experiment-defined.",
        ],
    }


def write_results(trials: list[TrialRecord], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "trials.jsonl"
    summary_path = output_dir / "summary.json"

    with raw_path.open("w", encoding="utf-8", newline="\n") as handle:
        for trial in trials:
            handle.write(json.dumps(trial.to_dict(), sort_keys=True, separators=(",", ":")))
            handle.write("\n")

    summary_path.write_text(
        json.dumps(summarize(trials), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return raw_path, summary_path
