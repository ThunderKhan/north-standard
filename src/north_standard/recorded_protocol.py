"""Protocol hardening helpers for Mode R calibration and replay."""

from __future__ import annotations

from typing import Any, Sequence

from .canonical import canonical_sha256
from .recorded_real import RecordedRealError, validate_calibration, validate_trace

_CHALLENGE_PROFILE_FIELDS = (
    "elements",
    "compute_inner_iterations",
    "warmup_iterations",
)


def challenge_profile(trace: dict[str, Any]) -> dict[str, int]:
    validate_trace(trace)
    challenge = trace["challenge"]
    return {field: int(challenge[field]) for field in _CHALLENGE_PROFILE_FIELDS}


def challenge_fingerprint(trace: dict[str, Any]) -> str:
    return canonical_sha256(challenge_profile(trace))


def bind_calibration_to_challenge(
    calibration: dict[str, Any], traces: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """Attach the exact benchmark shape used to create a calibration.

    Measurement iteration count is intentionally excluded: it controls capture length,
    not the per-sample challenge primitive. Elements, FMA work and warmup are bound.
    """

    validate_calibration(calibration)
    if not traces:
        raise RecordedRealError("challenge binding requires at least one calibration trace")
    fingerprints = {challenge_fingerprint(trace) for trace in traces}
    if len(fingerprints) != 1:
        raise RecordedRealError("calibration traces use different challenge configurations")
    profile = challenge_profile(traces[0])
    return {
        **calibration,
        "challenge_fingerprint": next(iter(fingerprints)),
        "challenge_profile": profile,
    }


def validate_challenge_binding(
    calibration: dict[str, Any], traces: Sequence[dict[str, Any]]
) -> None:
    validate_calibration(calibration)
    expected = calibration.get("challenge_fingerprint")
    profile = calibration.get("challenge_profile")
    if not isinstance(expected, str) or len(expected) != 64:
        raise RecordedRealError(
            "calibration is not challenge-bound; rebuild it with calibrate_recorded.py"
        )
    if not isinstance(profile, dict):
        raise RecordedRealError("calibration challenge_profile is missing")
    normalized_profile = {field: profile.get(field) for field in _CHALLENGE_PROFILE_FIELDS}
    if canonical_sha256(normalized_profile) != expected:
        raise RecordedRealError("calibration challenge profile hash mismatch")
    for trace in traces:
        if challenge_fingerprint(trace) != expected:
            raise RecordedRealError("trace challenge configuration does not match calibration")
