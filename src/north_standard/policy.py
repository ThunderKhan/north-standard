"""Versioned verifier policy for the v0.1 research implementation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerifierPolicy:
    policy_id: str = "VERIFIER-v0.1"
    minimum_valid_challenges: int = 2
    minimum_breach_challenges: int = 2
    max_evidence_age_seconds: int = 3600
    reject_invalid_authentication: bool = True
    require_unique_nonces: bool = True

    def __post_init__(self) -> None:
        if self.minimum_valid_challenges < 1:
            raise ValueError("minimum_valid_challenges must be >= 1")
        if self.minimum_breach_challenges < 1:
            raise ValueError("minimum_breach_challenges must be >= 1")
        if self.minimum_breach_challenges > self.minimum_valid_challenges:
            raise ValueError(
                "minimum_breach_challenges cannot exceed minimum_valid_challenges"
            )
