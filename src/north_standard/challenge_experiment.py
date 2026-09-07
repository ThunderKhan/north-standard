"""Synthetic challenge-aware cheating experiment.

A provider cheats between challenge windows but restores healthy performance around
challenge times it can predict. The experiment compares predictable and hidden challenge
schedules using the real verifier's performance-claim logic.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from enum import Enum
import json
from pathlib import Path
from random import Random
from typing import Any

from .models import Decision, EvidenceBundle, EvidenceRecord, EvidenceType
from .simulator import Scenario, simulate_scenario
from .verifier import verify


class ChallengeSchedule(str, Enum):
    FIXED_PERIODIC = "fixed_periodic"
    PUBLIC_JITTER = "public_jitter"
    HIDDEN_JITTER = "hidden_jitter"
    HIDDEN_UNIFORM = "hidden_uniform"


@dataclass(frozen=True)
class ChallengeExperimentConfig:
    delivery_seconds: int = 600
    challenge_count: int = 6
    honesty_radius_seconds: int = 5
    jitter_seconds: int = 20
    honest_score: float = 0.95
    cheat_score: float = 0.55

    def __post_init__(self) -> None:
        if self.delivery_seconds < 60:
            raise ValueError("delivery_seconds must be >= 60")
        if self.challenge_count < 2:
            raise ValueError("challenge_count must be >= 2")
        if self.honesty_radius_seconds < 0:
            raise ValueError("honesty_radius_seconds must be non-negative")
        if self.jitter_seconds < self.honesty_radius_seconds:
            raise ValueError("jitter_seconds must be >= honesty_radius_seconds")
        if not (0 <= self.cheat_score < self.honest_score):
            raise ValueError("scores must satisfy 0 <= cheat_score < honest_score")


@dataclass(frozen=True)
class ChallengeTrial:
    schedule: ChallengeSchedule
    seed: int
    decision: Decision
    reason_codes: tuple[str, ...]
    actual_challenge_times: tuple[int, ...]
    attacker_predicted_times: tuple[int, ...]
    breach_challenges: int
    challenge_count: int
    estimated_cheat_fraction: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "challenge-aware-trial/0.1",
            "experiment_id": "challenge-aware-cheating-smoke/0.1",
            "mode": "SYNTHETIC",
            "ground_truth": "BREACH",
            "schedule": self.schedule.value,
            "seed": self.seed,
            "decision": self.decision.value,
            "reason_codes": list(self.reason_codes),
            "actual_challenge_times": list(self.actual_challenge_times),
            "attacker_predicted_times": list(self.attacker_predicted_times),
            "breach_challenges": self.breach_challenges,
            "challenge_count": self.challenge_count,
            "estimated_cheat_fraction": self.estimated_cheat_fraction,
            "publication_ready": False,
        }


def _fixed_times(config: ChallengeExperimentConfig) -> tuple[int, ...]:
    step = config.delivery_seconds / (config.challenge_count + 1)
    return tuple(round(step * (index + 1)) for index in range(config.challenge_count))


def _clamp_time(value: int, config: ChallengeExperimentConfig) -> int:
    return max(1, min(config.delivery_seconds - 1, value))


def challenge_times(
    schedule: ChallengeSchedule | str,
    seed: int,
    config: ChallengeExperimentConfig,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return (actual challenge times, times the attacker can predict)."""

    schedule = ChallengeSchedule(schedule)
    rng = Random(seed)
    fixed = _fixed_times(config)

    if schedule == ChallengeSchedule.FIXED_PERIODIC:
        return fixed, fixed

    if schedule == ChallengeSchedule.PUBLIC_JITTER:
        actual = tuple(
            sorted(
                _clamp_time(
                    base + rng.randint(-config.jitter_seconds, config.jitter_seconds),
                    config,
                )
                for base in fixed
            )
        )
        # The jitter seed/schedule is public, so the adversary knows the exact times.
        return actual, actual

    if schedule == ChallengeSchedule.HIDDEN_JITTER:
        actual = tuple(
            sorted(
                _clamp_time(
                    base + rng.randint(-config.jitter_seconds, config.jitter_seconds),
                    config,
                )
                for base in fixed
            )
        )
        return actual, fixed

    if schedule == ChallengeSchedule.HIDDEN_UNIFORM:
        actual = tuple(sorted(rng.sample(range(1, config.delivery_seconds), config.challenge_count)))
        return actual, fixed

    raise AssertionError(f"unhandled challenge schedule: {schedule.value}")


def _is_honest_at(
    challenge_time: int,
    predicted_times: tuple[int, ...],
    radius: int,
) -> bool:
    return any(abs(challenge_time - predicted) <= radius for predicted in predicted_times)


def _estimated_cheat_fraction(
    predicted_times: tuple[int, ...],
    config: ChallengeExperimentConfig,
) -> float:
    honest_seconds: set[int] = set()
    for predicted in predicted_times:
        start = max(0, predicted - config.honesty_radius_seconds)
        end = min(config.delivery_seconds, predicted + config.honesty_radius_seconds)
        honest_seconds.update(range(start, end + 1))
    fraction = 1.0 - min(len(honest_seconds), config.delivery_seconds) / config.delivery_seconds
    return round(max(0.0, fraction), 6)


def generate_challenge_aware_bundle(
    schedule: ChallengeSchedule | str,
    seed: int,
    config: ChallengeExperimentConfig | None = None,
) -> tuple[Any, EvidenceBundle, tuple[int, ...], tuple[int, ...], int, float]:
    config = config or ChallengeExperimentConfig()
    schedule = ChallengeSchedule(schedule)
    contract, base_bundle = simulate_scenario(Scenario.HEALTHY_SERVICE)
    actual_times, predicted_times = challenge_times(schedule, seed, config)

    records = [
        record for record in base_bundle.records if record.evidence_type != EvidenceType.CHALLENGE
    ]
    breach_count = 0
    for index, challenge_time in enumerate(actual_times):
        honest = _is_honest_at(
            challenge_time,
            predicted_times,
            config.honesty_radius_seconds,
        )
        score = config.honest_score if honest else config.cheat_score
        if not honest:
            breach_count += 1
        observed_at = contract.delivery_start + challenge_time
        records.append(
            EvidenceRecord(
                schema_version="evidence/0.1",
                evidence_id=f"challenge-aware-{schedule.value}-{seed}-{index}",
                evidence_type=EvidenceType.CHALLENGE,
                producer_id="verifier-challenge-runner",
                contract_id=contract.contract_id,
                session_id=contract.session_id,
                observed_at=observed_at,
                received_at=observed_at + 1,
                sequence_number=100 + index,
                payload={
                    "score": score,
                    "timed_out": False,
                    "schedule_mode": schedule.value,
                },
                nonce=f"nonce-challenge-aware-{schedule.value}-{seed}-{index}",
                authentication_valid=True,
                trust_tier="T1",
            )
        )

    records.sort(key=lambda record: (record.observed_at, record.evidence_id))
    bundle = replace(base_bundle, records=tuple(records))
    cheat_fraction = _estimated_cheat_fraction(predicted_times, config)
    if cheat_fraction <= 0:
        raise RuntimeError("challenge-aware adversary must cheat during part of the delivery window")
    return contract, bundle, actual_times, predicted_times, breach_count, cheat_fraction


def run_challenge_trial(
    schedule: ChallengeSchedule | str,
    seed: int,
    config: ChallengeExperimentConfig | None = None,
) -> ChallengeTrial:
    config = config or ChallengeExperimentConfig()
    schedule = ChallengeSchedule(schedule)
    contract, bundle, actual, predicted, breach_count, cheat_fraction = generate_challenge_aware_bundle(
        schedule, seed, config
    )
    result = verify(contract, bundle)
    return ChallengeTrial(
        schedule=schedule,
        seed=seed,
        decision=result.decision,
        reason_codes=tuple(result.reason_codes),
        actual_challenge_times=actual,
        attacker_predicted_times=predicted,
        breach_challenges=breach_count,
        challenge_count=config.challenge_count,
        estimated_cheat_fraction=cheat_fraction,
    )


def run_challenge_matrix(
    *,
    trials_per_schedule: int,
    base_seed: int,
    config: ChallengeExperimentConfig | None = None,
) -> list[ChallengeTrial]:
    if trials_per_schedule < 1:
        raise ValueError("trials_per_schedule must be >= 1")
    if base_seed < 0:
        raise ValueError("base_seed must be non-negative")
    config = config or ChallengeExperimentConfig()

    rows: list[ChallengeTrial] = []
    for schedule_index, schedule in enumerate(ChallengeSchedule):
        seed_base = base_seed + schedule_index * 1_000_003
        for trial_index in range(trials_per_schedule):
            rows.append(run_challenge_trial(schedule, seed_base + trial_index, config))
    return rows


def summarize_challenge_matrix(
    rows: list[ChallengeTrial],
    config: ChallengeExperimentConfig | None = None,
) -> dict[str, Any]:
    config = config or ChallengeExperimentConfig()
    by_schedule: dict[str, Any] = {}
    for schedule in ChallengeSchedule:
        selected = [row for row in rows if row.schedule == schedule]
        if not selected:
            continue
        counts = Counter(row.decision.value for row in selected)
        accepts = counts.get(Decision.ACCEPT.value, 0)
        rejects = counts.get(Decision.REJECT.value, 0)
        inconclusive = counts.get(Decision.INCONCLUSIVE.value, 0)
        total = len(selected)
        by_schedule[schedule.value] = {
            "trials": total,
            "false_accepts": accepts,
            "detected_rejects": rejects,
            "inconclusive": inconclusive,
            "false_accept_rate": accepts / total,
            "detection_rate": rejects / total,
            "inconclusive_rate": inconclusive / total,
            "challenge_count": config.challenge_count,
            "challenge_density_per_hour": config.challenge_count / (config.delivery_seconds / 3600),
            "mean_estimated_cheat_fraction": sum(
                row.estimated_cheat_fraction for row in selected
            ) / total,
        }

    return {
        "schema_version": "challenge-aware-summary/0.1",
        "experiment_id": "challenge-aware-cheating-smoke/0.1",
        "mode": "SYNTHETIC",
        "ground_truth": "BREACH",
        "publication_ready": False,
        "status": "SMOKE_ONLY_NOT_PUBLICATION_READY",
        "config": {
            "delivery_seconds": config.delivery_seconds,
            "challenge_count": config.challenge_count,
            "honesty_radius_seconds": config.honesty_radius_seconds,
            "jitter_seconds": config.jitter_seconds,
            "honest_score": config.honest_score,
            "cheat_score": config.cheat_score,
        },
        "schedules": by_schedule,
        "notes": [
            "Challenge count/density are scheduling proxies, not measured GPU compute overhead.",
            "The attacker model and challenge score distributions are synthetic.",
            "Final claims require held-out seeds, sensitivity sweeps, and recorded-real challenge runtime data.",
        ],
    }


def write_challenge_results(
    rows: list[ChallengeTrial],
    output_dir: Path,
    config: ChallengeExperimentConfig | None = None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "challenge_trials.jsonl"
    summary_path = output_dir / "challenge_summary.json"
    with raw_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row.to_dict(), sort_keys=True, separators=(",", ":")))
            handle.write("\n")
    summary_path.write_text(
        json.dumps(summarize_challenge_matrix(rows, config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return raw_path, summary_path
