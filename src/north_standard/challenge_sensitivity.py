"""Sensitivity sweeps for the challenge-aware cheating model.

The grid varies challenge frequency, the adversary's honesty window, and jitter width.
Every cell reports a Wilson interval for false-accept, detection, and abstention rates.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable

from .challenge_experiment import (
    ChallengeExperimentConfig,
    ChallengeSchedule,
    run_challenge_trial,
)
from .evaluation_protocol import wilson_interval
from .models import Decision


@dataclass(frozen=True)
class SensitivityCell:
    schedule: ChallengeSchedule
    challenge_count: int
    honesty_radius_seconds: int
    jitter_seconds: int
    trials: int
    false_accepts: int
    detected_rejects: int
    inconclusive: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schedule": self.schedule.value,
            "challenge_count": self.challenge_count,
            "honesty_radius_seconds": self.honesty_radius_seconds,
            "jitter_seconds": self.jitter_seconds,
            "trials": self.trials,
            "false_accepts": self.false_accepts,
            "detected_rejects": self.detected_rejects,
            "inconclusive": self.inconclusive,
            "false_accept_rate": wilson_interval(self.false_accepts, self.trials).to_dict(),
            "detection_rate": wilson_interval(self.detected_rejects, self.trials).to_dict(),
            "inconclusive_rate": wilson_interval(self.inconclusive, self.trials).to_dict(),
        }


def run_sensitivity_grid(
    *,
    challenge_counts: Iterable[int] = (2, 4, 6, 8, 12),
    honesty_radii_seconds: Iterable[int] = (2, 5, 10, 20),
    jitter_values_seconds: Iterable[int] = (10, 20, 40),
    trials_per_cell: int = 100,
    base_seed: int = 320_260_907,
    schedules: Iterable[ChallengeSchedule] = tuple(ChallengeSchedule),
) -> list[SensitivityCell]:
    if trials_per_cell < 1:
        raise ValueError("trials_per_cell must be >= 1")
    if base_seed < 0:
        raise ValueError("base_seed must be non-negative")

    counts = tuple(challenge_counts)
    radii = tuple(honesty_radii_seconds)
    jitters = tuple(jitter_values_seconds)
    schedule_values = tuple(schedules)
    if not counts or not radii or not jitters or not schedule_values:
        raise ValueError("sensitivity axes must not be empty")
    if any(value < 2 for value in counts):
        raise ValueError("challenge counts must be >= 2")
    if any(value < 0 for value in radii):
        raise ValueError("honesty radii must be non-negative")
    if any(value < 0 for value in jitters):
        raise ValueError("jitter values must be non-negative")

    cells: list[SensitivityCell] = []
    cell_index = 0
    for schedule in schedule_values:
        for challenge_count in counts:
            for radius in radii:
                for jitter in jitters:
                    # ChallengeExperimentConfig deliberately rejects a jitter interval
                    # smaller than the attacker's modeled honesty window.
                    if jitter < radius:
                        continue
                    config = ChallengeExperimentConfig(
                        challenge_count=challenge_count,
                        honesty_radius_seconds=radius,
                        jitter_seconds=jitter,
                    )
                    seed_base = base_seed + cell_index * 1_000_003
                    decisions = [
                        run_challenge_trial(schedule, seed_base + trial_index, config).decision
                        for trial_index in range(trials_per_cell)
                    ]
                    cells.append(
                        SensitivityCell(
                            schedule=schedule,
                            challenge_count=challenge_count,
                            honesty_radius_seconds=radius,
                            jitter_seconds=jitter,
                            trials=trials_per_cell,
                            false_accepts=sum(item == Decision.ACCEPT for item in decisions),
                            detected_rejects=sum(item == Decision.REJECT for item in decisions),
                            inconclusive=sum(item == Decision.INCONCLUSIVE for item in decisions),
                        )
                    )
                    cell_index += 1
    return cells


def summarize_sensitivity(cells: list[SensitivityCell]) -> dict[str, Any]:
    if not cells:
        raise ValueError("sensitivity grid must not be empty")

    fixed = [cell for cell in cells if cell.schedule == ChallengeSchedule.FIXED_PERIODIC]
    hidden = [
        cell
        for cell in cells
        if cell.schedule in {ChallengeSchedule.HIDDEN_JITTER, ChallengeSchedule.HIDDEN_UNIFORM}
    ]
    return {
        "schema_version": "challenge-sensitivity-summary/0.1",
        "experiment_id": "challenge-sensitivity-synthetic/0.1",
        "mode": "SYNTHETIC",
        "ground_truth": "BREACH",
        "status": "SENSITIVITY_SYNTHETIC_NOT_PUBLICATION_READY",
        "publication_ready": False,
        "cell_count": len(cells),
        "fixed_periodic_cells": len(fixed),
        "hidden_schedule_cells": len(hidden),
        "cells": [cell.to_dict() for cell in cells],
        "notes": [
            "Each confidence interval is a binomial Wilson interval over synthetic trials in one parameter cell.",
            "The sweep is designed to expose fragile parameter choices, not select a favorable headline result.",
            "Challenge count is not GPU overhead; real challenge runtime must be measured on recorded/live hardware.",
        ],
    }


def write_sensitivity_results(
    cells: list[SensitivityCell], output_dir: Path
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "sensitivity_cells.jsonl"
    summary_path = output_dir / "sensitivity_summary.json"
    with raw_path.open("w", encoding="utf-8", newline="\n") as handle:
        for cell in cells:
            handle.write(json.dumps(cell.to_dict(), sort_keys=True, separators=(",", ":")))
            handle.write("\n")
    summary_path.write_text(
        json.dumps(summarize_sensitivity(cells), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return raw_path, summary_path
