"""Held-out synthetic evaluation protocol and uncertainty reporting.

This module separates calibration and held-out seed namespaces and reports Wilson score
intervals for binomial error/abstention rates. It does not make synthetic results
publication-ready; it makes the evaluation mechanics harder to accidentally overstate.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from math import sqrt
from pathlib import Path
from typing import Any

from .experiments import GroundTruth, SyntheticCase, TrialRecord, run_trial
from .models import Decision


@dataclass(frozen=True)
class WilsonInterval:
    estimate: float
    lower: float
    upper: float
    confidence: float
    numerator: int
    denominator: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimate": self.estimate,
            "lower": self.lower,
            "upper": self.upper,
            "confidence": self.confidence,
            "numerator": self.numerator,
            "denominator": self.denominator,
        }


def wilson_interval(successes: int, total: int, *, z: float = 1.959963984540054) -> WilsonInterval:
    """Return a two-sided 95% Wilson score interval by default."""

    if total <= 0:
        raise ValueError("total must be positive")
    if successes < 0 or successes > total:
        raise ValueError("successes must satisfy 0 <= successes <= total")
    if z <= 0:
        raise ValueError("z must be positive")

    p_hat = successes / total
    z2 = z * z
    denominator = 1.0 + z2 / total
    center = (p_hat + z2 / (2.0 * total)) / denominator
    margin = (
        z
        * sqrt((p_hat * (1.0 - p_hat) / total) + (z2 / (4.0 * total * total)))
        / denominator
    )
    return WilsonInterval(
        estimate=p_hat,
        lower=max(0.0, center - margin),
        upper=min(1.0, center + margin),
        confidence=0.95,
        numerator=successes,
        denominator=total,
    )


@dataclass(frozen=True)
class SeedPartition:
    split_id: str
    calibration_base_seed: int
    heldout_base_seed: int
    calibration_trials_per_scenario: int
    heldout_trials_per_scenario: int

    def __post_init__(self) -> None:
        if self.calibration_base_seed < 0 or self.heldout_base_seed < 0:
            raise ValueError("base seeds must be non-negative")
        if self.calibration_trials_per_scenario < 1 or self.heldout_trials_per_scenario < 1:
            raise ValueError("trial counts must be >= 1")
        if self.calibration_base_seed == self.heldout_base_seed:
            raise ValueError("calibration and held-out base seeds must differ")

    def seeds_for(self, case: SyntheticCase, *, heldout: bool) -> tuple[int, ...]:
        scenario_index = list(SyntheticCase).index(case)
        base = self.heldout_base_seed if heldout else self.calibration_base_seed
        count = (
            self.heldout_trials_per_scenario
            if heldout
            else self.calibration_trials_per_scenario
        )
        scenario_base = base + scenario_index * 1_000_003
        return tuple(scenario_base + index for index in range(count))

    def assert_disjoint(self) -> None:
        calibration = {
            seed
            for case in SyntheticCase
            for seed in self.seeds_for(case, heldout=False)
        }
        heldout = {
            seed
            for case in SyntheticCase
            for seed in self.seeds_for(case, heldout=True)
        }
        overlap = calibration.intersection(heldout)
        if overlap:
            raise ValueError(f"calibration/held-out seed overlap: {sorted(overlap)[:5]}")

    def to_dict(self) -> dict[str, Any]:
        self.assert_disjoint()
        return {
            "split_id": self.split_id,
            "calibration_base_seed": self.calibration_base_seed,
            "heldout_base_seed": self.heldout_base_seed,
            "calibration_trials_per_scenario": self.calibration_trials_per_scenario,
            "heldout_trials_per_scenario": self.heldout_trials_per_scenario,
            "scenario_seed_ranges": {
                case.value: {
                    "calibration": [
                        min(self.seeds_for(case, heldout=False)),
                        max(self.seeds_for(case, heldout=False)),
                    ],
                    "heldout": [
                        min(self.seeds_for(case, heldout=True)),
                        max(self.seeds_for(case, heldout=True)),
                    ],
                }
                for case in SyntheticCase
            },
        }


DEFAULT_PARTITION = SeedPartition(
    split_id="synthetic-v0.1-calibration-heldout",
    calibration_base_seed=20_260_907,
    heldout_base_seed=120_260_907,
    calibration_trials_per_scenario=50,
    heldout_trials_per_scenario=200,
)


def run_partition(
    partition: SeedPartition = DEFAULT_PARTITION,
) -> tuple[list[TrialRecord], list[TrialRecord]]:
    partition.assert_disjoint()
    calibration: list[TrialRecord] = []
    heldout: list[TrialRecord] = []
    for case in SyntheticCase:
        calibration.extend(
            run_trial(case, seed)
            for seed in partition.seeds_for(case, heldout=False)
        )
        heldout.extend(
            run_trial(case, seed)
            for seed in partition.seeds_for(case, heldout=True)
        )
    return calibration, heldout


def _interval(successes: int, total: int) -> dict[str, Any]:
    return wilson_interval(successes, total).to_dict()


def heldout_summary(
    heldout: list[TrialRecord],
    partition: SeedPartition = DEFAULT_PARTITION,
) -> dict[str, Any]:
    if not heldout:
        raise ValueError("heldout trials must not be empty")

    compliant = [row for row in heldout if row.ground_truth == GroundTruth.COMPLIANT]
    breaches = [row for row in heldout if row.ground_truth == GroundTruth.BREACH]
    false_accepts = [row for row in breaches if row.decision == Decision.ACCEPT]
    false_rejects = [row for row in compliant if row.decision == Decision.REJECT]
    inconclusive = [row for row in heldout if row.decision == Decision.INCONCLUSIVE]
    compliant_inconclusive = [
        row for row in compliant if row.decision == Decision.INCONCLUSIVE
    ]
    breach_inconclusive = [
        row for row in breaches if row.decision == Decision.INCONCLUSIVE
    ]

    per_scenario: dict[str, Any] = {}
    for case in SyntheticCase:
        selected = [row for row in heldout if row.scenario == case.value]
        if not selected:
            continue
        accepts = sum(row.decision == Decision.ACCEPT for row in selected)
        rejects = sum(row.decision == Decision.REJECT for row in selected)
        abstains = sum(row.decision == Decision.INCONCLUSIVE for row in selected)
        per_scenario[case.value] = {
            "trials": len(selected),
            "accept": accepts,
            "reject": rejects,
            "inconclusive": abstains,
            "inconclusive_interval": _interval(abstains, len(selected)),
        }

    return {
        "schema_version": "heldout-evaluation-summary/0.1",
        "experiment_id": "synthetic-heldout/0.1",
        "mode": "SYNTHETIC",
        "status": "HELDOUT_SYNTHETIC_NOT_PUBLICATION_READY",
        "publication_ready": False,
        "partition": partition.to_dict(),
        "heldout_trials": len(heldout),
        "compliant_trials": len(compliant),
        "breach_trials": len(breaches),
        "far": _interval(len(false_accepts), len(breaches)),
        "frr": _interval(len(false_rejects), len(compliant)),
        "inconclusive_rate": _interval(len(inconclusive), len(heldout)),
        "inconclusive_rate_compliant": _interval(
            len(compliant_inconclusive), len(compliant)
        ),
        "inconclusive_rate_breach": _interval(len(breach_inconclusive), len(breaches)),
        "per_scenario": per_scenario,
        "notes": [
            "Wilson intervals report finite-sample uncertainty; zero observed errors do not imply zero true error.",
            "The held-out split is disjoint from calibration by construction, but no production threshold claim is made.",
            "Synthetic held-out evaluation remains non-publication-ready until real-hardware provenance and broader attacks are added.",
        ],
    }


def write_heldout_results(
    calibration: list[TrialRecord],
    heldout: list[TrialRecord],
    output_dir: Path,
    partition: SeedPartition = DEFAULT_PARTITION,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "partition_manifest.json"
    heldout_path = output_dir / "heldout_trials.jsonl"
    summary_path = output_dir / "heldout_summary.json"

    manifest = {
        "schema_version": "evaluation-partition/0.1",
        "partition": partition.to_dict(),
        "calibration_trial_count": len(calibration),
        "heldout_trial_count": len(heldout),
        "calibration_results_persisted": False,
        "reason": "Calibration trials are generated to validate split mechanics; this milestone does not tune policy from them.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with heldout_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in heldout:
            handle.write(json.dumps(row.to_dict(), sort_keys=True, separators=(",", ":")))
            handle.write("\n")

    summary_path.write_text(
        json.dumps(heldout_summary(heldout, partition), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path, heldout_path, summary_path
