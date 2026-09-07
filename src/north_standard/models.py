"""Core v0.1 data model.

The model intentionally separates contract semantics, evidence, appraisal results,
and eventual settlement policy. Ground-truth labels belong only in the simulator and
experiment harness; the verifier never receives them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from .canonical import canonical_sha256


class Decision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    INCONCLUSIVE = "INCONCLUSIVE"


class ClaimState(str, Enum):
    AFFIRMING = "AFFIRMING"
    CONTRADICTING = "CONTRADICTING"
    UNKNOWN = "UNKNOWN"
    NOT_EVALUATED = "NOT_EVALUATED"
    INVALID = "INVALID"


class EvidenceType(str, Enum):
    SESSION_BINDING = "SESSION_BINDING"
    RUNTIME_CHECK = "RUNTIME_CHECK"
    TELEMETRY = "TELEMETRY"
    CHALLENGE = "CHALLENGE"
    EXTERNAL_PROBE = "EXTERNAL_PROBE"
    HARDWARE_ATTESTATION = "HARDWARE_ATTESTATION"
    ADMIN_EVENT = "ADMIN_EVENT"


MANDATORY_V01_CLAIMS = (
    "session.binding",
    "service.runtime",
    "service.availability",
    "service.performance",
)


@dataclass(frozen=True)
class ComputeContract:
    schema_version: str
    contract_id: str
    contract_class_id: str
    provider_id: str
    buyer_id: str
    session_id: str
    runtime_profile_id: str
    delivery_start: int
    duration_seconds: int
    sla_policy_id: str
    benchmark_profile_id: str
    performance_min_score: float
    verifier_policy_id: str
    settlement_policy_id: str
    evidence_schema_version: str = "evidence/0.1"
    mandatory_claims: tuple[str, ...] = MANDATORY_V01_CLAIMS
    research_mode: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != "compute-contract/0.1":
            raise ValueError("unsupported compute contract schema_version")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if not self.contract_id or not self.session_id:
            raise ValueError("contract_id and session_id are required")
        if self.performance_min_score < 0:
            raise ValueError("performance_min_score must be non-negative")

    @property
    def delivery_end(self) -> int:
        return self.delivery_start + self.duration_seconds

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mandatory_claims"] = list(self.mandatory_claims)
        return data

    @property
    def semantic_hash(self) -> str:
        return canonical_sha256(self.to_dict())


@dataclass(frozen=True)
class EvidenceRecord:
    schema_version: str
    evidence_id: str
    evidence_type: EvidenceType
    producer_id: str
    contract_id: str
    session_id: str
    observed_at: int
    received_at: int
    sequence_number: int
    payload: dict[str, Any]
    nonce: str | None = None
    replay_domain: str = "north-standard/v0.1"
    authentication_valid: bool = True
    trust_tier: str = "T1"

    def __post_init__(self) -> None:
        if self.schema_version != "evidence/0.1":
            raise ValueError("unsupported evidence schema_version")
        if self.sequence_number < 0:
            raise ValueError("sequence_number must be non-negative")
        if self.received_at < self.observed_at:
            raise ValueError("received_at cannot precede observed_at")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_type"] = self.evidence_type.value
        return data


@dataclass(frozen=True)
class EvidenceBundle:
    contract_id: str
    session_id: str
    records: tuple[EvidenceRecord, ...]
    schema_version: str = "evidence-bundle/0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "session_id": self.session_id,
            "records": [record.to_dict() for record in self.records],
        }

    @property
    def bundle_root(self) -> str:
        return canonical_sha256(self.to_dict())


@dataclass(frozen=True)
class ClaimResult:
    claim_id: str
    state: ClaimState
    reason_codes: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "state": self.state.value,
            "reason_codes": list(self.reason_codes),
            "evidence_refs": list(self.evidence_refs),
            "metrics": self.metrics,
        }


@dataclass(frozen=True)
class VerifierResult:
    schema_version: str
    contract_id: str
    session_id: str
    verifier_policy_id: str
    evidence_bundle_root: str
    claims: dict[str, ClaimResult]
    decision: Decision
    reason_codes: tuple[str, ...]
    verifier_build_id: str
    research_mode: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "session_id": self.session_id,
            "verifier_policy_id": self.verifier_policy_id,
            "evidence_bundle_root": self.evidence_bundle_root,
            "claims": {k: v.to_dict() for k, v in sorted(self.claims.items())},
            "overall": {
                "decision": self.decision.value,
                "reason_codes": list(self.reason_codes),
            },
            "audit": {
                "verifier_build_id": self.verifier_build_id,
                "research_mode": self.research_mode,
            },
        }

    @property
    def result_hash(self) -> str:
        return canonical_sha256(self.to_dict())
