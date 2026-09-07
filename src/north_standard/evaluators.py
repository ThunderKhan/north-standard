"""Research baselines and ablations for North Standard verifier evaluation.

These evaluators are experiment-only comparators. Only `FULL` represents the current
settlement verifier. Baselines intentionally throw away evidence classes; ablations
remove one part of the full verifier to measure its contribution.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from enum import Enum
import json
from pathlib import Path
from time import perf_counter_ns
from typing import Any, Iterable

from .experiments import CASE_SPECS, GroundTruth, SyntheticCase, generate_case_evidence
from .models import ComputeContract, Decision, EvidenceBundle, EvidenceType
from .policy import VerifierPolicy
from .verifier import verify


class Evaluator(str, Enum):
    FULL = "FULL"
    B0_SELF_REPORT = "B0_SELF_REPORT"
    B3_CHALLENGE_ONLY = "B3_CHALLENGE_ONLY"
    B5_EXTERNAL_PROBE_ONLY = "B5_EXTERNAL_PROBE_ONLY"
    ABLATION_NO_BINDING = "ABLATION_NO_BINDING"
    ABLATION_NO_TELEMETRY = "ABLATION_NO_TELEMETRY"
    ABLATION_NO_EXTERNAL_PROBE = "ABLATION_NO_EXTERNAL_PROBE"
    ABLATION_NO_ABSTENTION = "ABLATION_NO_ABSTENTION"


DEFAULT_EVALUATORS = tuple(Evaluator)


@dataclass(frozen=True)
class EvaluationOutcome:
    decision: Decision
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ComparisonRecord:
    experiment_id: str
    evaluator_id: Evaluator
    scenario: SyntheticCase
    attack_family: str
    ground_truth: GroundTruth
    seed: int
    mode: str
    decision: Decision
    reason_codes: tuple[str, ...]
    runtime_ns: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "evaluator-comparison-trial/0.1",
            "experiment_id": self.experiment_id,
            "evaluator_id": self.evaluator_id.value,
            "scenario": self.scenario.value,
            "attack_family": self.attack_family,
            "ground_truth": self.ground_truth.value,
            "seed": self.seed,
            "mode": self.mode,
            "decision": self.decision.value,
            "reason_codes": list(self.reason_codes),
            "runtime_ns": self.runtime_ns,
            "publication_ready": False,
        }


def _baseline_self_report(bundle: EvidenceBundle) -> EvaluationOutcome:
    telemetry = [record for record in bundle.records if record.evidence_type == EvidenceType.TELEMETRY]
    if not telemetry:
        return EvaluationOutcome(Decision.INCONCLUSIVE, ("SELF_REPORT_MISSING",))
    if any(record.payload.get("service_state") == "UNAVAILABLE" for record in telemetry):
        return EvaluationOutcome(Decision.REJECT, ("SELF_REPORTED_UNAVAILABLE",))
    if any(record.payload.get("service_state") == "HEALTHY" for record in telemetry):
        return EvaluationOutcome(Decision.ACCEPT, ("SELF_REPORTED_HEALTHY",))
    return EvaluationOutcome(Decision.INCONCLUSIVE, ("SELF_REPORT_UNKNOWN",))


def _baseline_challenge_only(
    contract: ComputeContract,
    bundle: EvidenceBundle,
) -> EvaluationOutcome:
    policy = VerifierPolicy(policy_id=contract.verifier_policy_id)
    challenges = [
        record
        for record in bundle.records
        if record.evidence_type == EvidenceType.CHALLENGE
        and record.authentication_valid
        and record.contract_id == contract.contract_id
        and record.session_id == contract.session_id
        and not bool(record.payload.get("timed_out", False))
        and isinstance(record.payload.get("score"), (int, float))
    ]
    if len(challenges) < policy.minimum_valid_challenges:
        return EvaluationOutcome(Decision.INCONCLUSIVE, ("CHALLENGE_ONLY_INSUFFICIENT",))
    breaches = [
        record
        for record in challenges
        if float(record.payload["score"]) < contract.performance_min_score
    ]
    if len(breaches) >= policy.minimum_breach_challenges:
        return EvaluationOutcome(Decision.REJECT, ("CHALLENGE_ONLY_BREACH",))
    if breaches:
        return EvaluationOutcome(Decision.INCONCLUSIVE, ("CHALLENGE_ONLY_MIXED",))
    return EvaluationOutcome(Decision.ACCEPT, ("CHALLENGE_ONLY_PASS",))


def _baseline_external_probe(bundle: EvidenceBundle) -> EvaluationOutcome:
    probes = [record for record in bundle.records if record.evidence_type == EvidenceType.EXTERNAL_PROBE]
    if not probes:
        return EvaluationOutcome(Decision.INCONCLUSIVE, ("EXTERNAL_PROBE_MISSING",))
    if any(
        record.payload.get("result") == "FAILURE"
        and record.payload.get("attribution") == "PROVIDER"
        for record in probes
    ):
        return EvaluationOutcome(Decision.REJECT, ("EXTERNAL_PROBE_PROVIDER_FAILURE",))
    if any(
        record.payload.get("result") == "FAILURE"
        and record.payload.get("attribution") in {None, "UNKNOWN", "NETWORK"}
        for record in probes
    ):
        return EvaluationOutcome(Decision.INCONCLUSIVE, ("EXTERNAL_PROBE_AMBIGUOUS",))
    if any(record.payload.get("result") == "SUCCESS" for record in probes):
        return EvaluationOutcome(Decision.ACCEPT, ("EXTERNAL_PROBE_SUCCESS",))
    return EvaluationOutcome(Decision.INCONCLUSIVE, ("EXTERNAL_PROBE_UNKNOWN",))


def _full(contract: ComputeContract, bundle: EvidenceBundle) -> EvaluationOutcome:
    result = verify(contract, bundle)
    return EvaluationOutcome(result.decision, tuple(result.reason_codes))


def evaluate(
    evaluator: Evaluator | str,
    contract: ComputeContract,
    bundle: EvidenceBundle,
) -> EvaluationOutcome:
    evaluator = Evaluator(evaluator)
    if evaluator == Evaluator.FULL:
        return _full(contract, bundle)
    if evaluator == Evaluator.B0_SELF_REPORT:
        return _baseline_self_report(bundle)
    if evaluator == Evaluator.B3_CHALLENGE_ONLY:
        return _baseline_challenge_only(contract, bundle)
    if evaluator == Evaluator.B5_EXTERNAL_PROBE_ONLY:
        return _baseline_external_probe(bundle)

    if evaluator == Evaluator.ABLATION_NO_BINDING:
        ablated_contract = replace(
            contract,
            mandatory_claims=tuple(
                claim for claim in contract.mandatory_claims if claim != "session.binding"
            ),
        )
        return _full(ablated_contract, bundle)

    if evaluator == Evaluator.ABLATION_NO_TELEMETRY:
        ablated_bundle = replace(
            bundle,
            records=tuple(
                record
                for record in bundle.records
                if record.evidence_type != EvidenceType.TELEMETRY
            ),
        )
        return _full(contract, ablated_bundle)

    if evaluator == Evaluator.ABLATION_NO_EXTERNAL_PROBE:
        ablated_bundle = replace(
            bundle,
            records=tuple(
                record
                for record in bundle.records
                if record.evidence_type != EvidenceType.EXTERNAL_PROBE
            ),
        )
        return _full(contract, ablated_bundle)

    if evaluator == Evaluator.ABLATION_NO_ABSTENTION:
        outcome = _full(contract, bundle)
        if outcome.decision == Decision.INCONCLUSIVE:
            return EvaluationOutcome(
                Decision.ACCEPT,
                tuple(outcome.reason_codes) + ("ABSTENTION_DISABLED_ACCEPT_DEFAULT",),
            )
        return outcome

    raise AssertionError(f"unhandled evaluator: {evaluator.value}")


def run_comparison_matrix(
    *,
    trials_per_scenario: int,
    base_seed: int,
    evaluators: Iterable[Evaluator] = DEFAULT_EVALUATORS,
) -> list[ComparisonRecord]:
    if trials_per_scenario < 1:
        raise ValueError("trials_per_scenario must be >= 1")
    if base_seed < 0:
        raise ValueError("base_seed must be non-negative")

    evaluator_list = tuple(evaluators)
    if not evaluator_list:
        raise ValueError("at least one evaluator is required")

    rows: list[ComparisonRecord] = []
    for scenario_index, case in enumerate(SyntheticCase):
        spec = CASE_SPECS[case]
        seed_base = base_seed + scenario_index * 1_000_003
        for trial_index in range(trials_per_scenario):
            seed = seed_base + trial_index
            contract, bundle = generate_case_evidence(case, seed)
            for evaluator in evaluator_list:
                start_ns = perf_counter_ns()
                outcome = evaluate(evaluator, contract, bundle)
                runtime_ns = perf_counter_ns() - start_ns
                rows.append(
                    ComparisonRecord(
                        experiment_id="synthetic-evaluator-comparison/0.1",
                        evaluator_id=evaluator,
                        scenario=case,
                        attack_family=spec.attack_family,
                        ground_truth=spec.ground_truth,
                        seed=seed,
                        mode="SYNTHETIC",
                        decision=outcome.decision,
                        reason_codes=outcome.reason_codes,
                        runtime_ns=runtime_ns,
                    )
                )
    return rows


def _rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _metrics(rows: list[ComparisonRecord]) -> dict[str, Any]:
    compliant = [row for row in rows if row.ground_truth == GroundTruth.COMPLIANT]
    breaches = [row for row in rows if row.ground_truth == GroundTruth.BREACH]
    false_accepts = [row for row in breaches if row.decision == Decision.ACCEPT]
    false_rejects = [row for row in compliant if row.decision == Decision.REJECT]
    inconclusive = [row for row in rows if row.decision == Decision.INCONCLUSIVE]
    return {
        "total_trials": len(rows),
        "compliant_trials": len(compliant),
        "breach_trials": len(breaches),
        "false_accepts": len(false_accepts),
        "false_rejects": len(false_rejects),
        "inconclusive_trials": len(inconclusive),
        "far": _rate(len(false_accepts), len(breaches)),
        "frr": _rate(len(false_rejects), len(compliant)),
        "inconclusive_rate": _rate(len(inconclusive), len(rows)),
        "decision_counts": dict(Counter(row.decision.value for row in rows)),
    }


def summarize_comparison(rows: list[ComparisonRecord]) -> dict[str, Any]:
    by_evaluator: dict[str, Any] = {}
    for evaluator in DEFAULT_EVALUATORS:
        evaluator_rows = [row for row in rows if row.evaluator_id == evaluator]
        if evaluator_rows:
            by_evaluator[evaluator.value] = _metrics(evaluator_rows)

    return {
        "schema_version": "evaluator-comparison-summary/0.1",
        "experiment_id": "synthetic-evaluator-comparison/0.1",
        "mode": "SYNTHETIC",
        "publication_ready": False,
        "status": "SMOKE_ONLY_NOT_PUBLICATION_READY",
        "evaluators": by_evaluator,
        "notes": [
            "Baselines and ablations are research comparators, not settlement implementations.",
            "Smoke comparison numbers are not publication or pitch claims.",
            "B0/B3/B5 names correspond only to the explicitly implemented evidence subsets documented in the repository.",
        ],
    }


def write_comparison_results(
    rows: list[ComparisonRecord], output_dir: Path
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "comparison_trials.jsonl"
    summary_path = output_dir / "comparison_summary.json"
    with raw_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row.to_dict(), sort_keys=True, separators=(",", ":")))
            handle.write("\n")
    summary_path.write_text(
        json.dumps(summarize_comparison(rows), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return raw_path, summary_path
