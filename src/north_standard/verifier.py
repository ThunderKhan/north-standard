"""Deterministic contract-bound verifier.

This is intentionally conservative. Missing or conflicting mandatory evidence becomes
INCONCLUSIVE rather than silently becoming success. The engine appraises evidence only;
it does not contain financial settlement logic.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

from .models import (
    ClaimResult,
    ClaimState,
    ComputeContract,
    Decision,
    EvidenceBundle,
    EvidenceRecord,
    EvidenceType,
    VerifierResult,
)
from .policy import VerifierPolicy

VERIFIER_BUILD_ID = "north-standard-python/v0.1"


def _refs(records: Iterable[EvidenceRecord]) -> tuple[str, ...]:
    return tuple(record.evidence_id for record in records)


def _records_of(bundle: EvidenceBundle, evidence_type: EvidenceType) -> list[EvidenceRecord]:
    return [r for r in bundle.records if r.evidence_type == evidence_type]


def _binding_claim(
    contract: ComputeContract,
    bundle: EvidenceBundle,
    policy: VerifierPolicy,
) -> ClaimResult:
    records = _records_of(bundle, EvidenceType.SESSION_BINDING)
    if not records:
        return ClaimResult("session.binding", ClaimState.UNKNOWN, ("SESSION_BINDING_MISSING",))

    wrong_contract = [r for r in records if r.contract_id != contract.contract_id]
    if wrong_contract or bundle.contract_id != contract.contract_id:
        return ClaimResult(
            "session.binding",
            ClaimState.CONTRADICTING,
            ("SESSION_CONTRACT_MISMATCH",),
            _refs(wrong_contract or records),
        )

    wrong_session = [r for r in records if r.session_id != contract.session_id]
    if wrong_session or bundle.session_id != contract.session_id:
        return ClaimResult(
            "session.binding",
            ClaimState.CONTRADICTING,
            ("SESSION_ID_MISMATCH",),
            _refs(wrong_session or records),
        )

    invalid_auth = [r for r in records if not r.authentication_valid]
    if invalid_auth:
        state = ClaimState.INVALID if policy.reject_invalid_authentication else ClaimState.UNKNOWN
        return ClaimResult(
            "session.binding",
            state,
            ("SESSION_SIGNATURE_INVALID",),
            _refs(invalid_auth),
        )

    nonces = [r.nonce for r in records if r.nonce is not None]
    if policy.require_unique_nonces:
        duplicates = [nonce for nonce, count in Counter(nonces).items() if count > 1]
        if duplicates:
            return ClaimResult(
                "session.binding",
                ClaimState.CONTRADICTING,
                ("EVIDENCE_NONCE_REPLAY",),
                _refs(records),
                {"duplicate_nonce_count": len(duplicates)},
            )

    return ClaimResult("session.binding", ClaimState.AFFIRMING, evidence_refs=_refs(records))


def _runtime_claim(contract: ComputeContract, bundle: EvidenceBundle) -> ClaimResult:
    records = _records_of(bundle, EvidenceType.RUNTIME_CHECK)
    valid = [
        r
        for r in records
        if r.contract_id == contract.contract_id
        and r.session_id == contract.session_id
        and r.authentication_valid
    ]
    if not valid:
        return ClaimResult("service.runtime", ClaimState.UNKNOWN, ("RUNTIME_EVIDENCE_MISSING",))

    incompatible = [
        r
        for r in valid
        if not bool(r.payload.get("usable", False))
        or r.payload.get("runtime_profile_id") != contract.runtime_profile_id
    ]
    if incompatible:
        return ClaimResult(
            "service.runtime",
            ClaimState.CONTRADICTING,
            ("RUNTIME_PROFILE_BREACH",),
            _refs(incompatible),
        )

    return ClaimResult("service.runtime", ClaimState.AFFIRMING, evidence_refs=_refs(valid))


def _performance_claim(
    contract: ComputeContract,
    bundle: EvidenceBundle,
    policy: VerifierPolicy,
) -> ClaimResult:
    records = _records_of(bundle, EvidenceType.CHALLENGE)
    valid = [
        r
        for r in records
        if r.contract_id == contract.contract_id
        and r.session_id == contract.session_id
        and r.authentication_valid
        and not bool(r.payload.get("timed_out", False))
        and isinstance(r.payload.get("score"), (int, float))
    ]

    if len(valid) < policy.minimum_valid_challenges:
        return ClaimResult(
            "service.performance",
            ClaimState.UNKNOWN,
            ("CHALLENGE_INSUFFICIENT_COUNT",),
            _refs(valid),
            {"valid_challenges": len(valid), "required": policy.minimum_valid_challenges},
        )

    scores = [float(r.payload["score"]) for r in valid]
    breach_records = [
        r for r in valid if float(r.payload["score"]) < contract.performance_min_score
    ]

    metrics = {
        "valid_challenges": len(valid),
        "breach_challenges": len(breach_records),
        "minimum_score": min(scores),
        "maximum_score": max(scores),
        "mean_score": sum(scores) / len(scores),
        "contract_floor": contract.performance_min_score,
        "threshold_status": "EXPERIMENT_DEFINED" if contract.research_mode else "CONTRACT_DEFINED",
    }

    if len(breach_records) >= policy.minimum_breach_challenges:
        return ClaimResult(
            "service.performance",
            ClaimState.CONTRADICTING,
            ("CHALLENGE_PERFORMANCE_BREACH",),
            _refs(breach_records),
            metrics,
        )

    if breach_records:
        return ClaimResult(
            "service.performance",
            ClaimState.UNKNOWN,
            ("CHALLENGE_MIXED_PERFORMANCE",),
            _refs(valid),
            metrics,
        )

    return ClaimResult(
        "service.performance",
        ClaimState.AFFIRMING,
        evidence_refs=_refs(valid),
        metrics=metrics,
    )


def _availability_claim(contract: ComputeContract, bundle: EvidenceBundle) -> ClaimResult:
    telemetry = [
        r
        for r in _records_of(bundle, EvidenceType.TELEMETRY)
        if r.contract_id == contract.contract_id
        and r.session_id == contract.session_id
        and r.authentication_valid
    ]
    probes = [
        r
        for r in _records_of(bundle, EvidenceType.EXTERNAL_PROBE)
        if r.contract_id == contract.contract_id
        and r.session_id == contract.session_id
        and r.authentication_valid
    ]
    challenges = [
        r
        for r in _records_of(bundle, EvidenceType.CHALLENGE)
        if r.contract_id == contract.contract_id
        and r.session_id == contract.session_id
        and r.authentication_valid
    ]

    provider_fail_probes = [
        r
        for r in probes
        if r.payload.get("result") == "FAILURE"
        and r.payload.get("attribution") == "PROVIDER"
    ]
    provider_fail_telemetry = [r for r in telemetry if r.payload.get("service_state") == "UNAVAILABLE"]
    timed_out_challenges = [
        r
        for r in challenges
        if bool(r.payload.get("timed_out", False))
        and r.payload.get("timeout_attribution") == "PROVIDER"
    ]

    if provider_fail_probes and (provider_fail_telemetry or timed_out_challenges):
        refs = provider_fail_probes + provider_fail_telemetry + timed_out_challenges
        return ClaimResult(
            "service.availability",
            ClaimState.CONTRADICTING,
            ("AVAILABILITY_PROVIDER_FAILURE",),
            _refs(refs),
        )

    ambiguous_failures = [
        r
        for r in probes
        if r.payload.get("result") == "FAILURE"
        and r.payload.get("attribution") in {None, "UNKNOWN", "NETWORK"}
    ]
    if ambiguous_failures:
        return ClaimResult(
            "service.availability",
            ClaimState.UNKNOWN,
            ("AVAILABILITY_EVIDENCE_CONFLICT",),
            _refs(ambiguous_failures + telemetry + challenges),
        )

    healthy_telemetry = [r for r in telemetry if r.payload.get("service_state") == "HEALTHY"]
    successful_probes = [r for r in probes if r.payload.get("result") == "SUCCESS"]
    successful_challenges = [r for r in challenges if not bool(r.payload.get("timed_out", False))]

    if healthy_telemetry and (successful_probes or successful_challenges):
        return ClaimResult(
            "service.availability",
            ClaimState.AFFIRMING,
            evidence_refs=_refs(healthy_telemetry + successful_probes + successful_challenges),
        )

    return ClaimResult(
        "service.availability",
        ClaimState.UNKNOWN,
        ("AVAILABILITY_EVIDENCE_INSUFFICIENT",),
        _refs(telemetry + probes + challenges),
    )


def _bundle_integrity_errors(
    contract: ComputeContract,
    bundle: EvidenceBundle,
) -> tuple[str, ...]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_sequences: dict[str, set[int]] = defaultdict(set)

    for record in bundle.records:
        if record.evidence_id in seen_ids:
            errors.append("DUPLICATE_EVIDENCE_ID")
        seen_ids.add(record.evidence_id)

        key = f"{record.producer_id}:{record.session_id}"
        if record.sequence_number in seen_sequences[key]:
            errors.append("DUPLICATE_SEQUENCE_NUMBER")
        seen_sequences[key].add(record.sequence_number)

        if record.observed_at < contract.delivery_start - 60:
            errors.append("EVIDENCE_BEFORE_DELIVERY_WINDOW")
        if record.observed_at > contract.delivery_end + 60:
            errors.append("EVIDENCE_AFTER_DELIVERY_WINDOW")

    return tuple(sorted(set(errors)))


def verify(
    contract: ComputeContract,
    bundle: EvidenceBundle,
    policy: VerifierPolicy | None = None,
) -> VerifierResult:
    """Appraise an evidence bundle and return a deterministic verifier result."""

    policy = policy or VerifierPolicy(policy_id=contract.verifier_policy_id)
    if policy.policy_id != contract.verifier_policy_id:
        raise ValueError("verifier policy mismatch")

    integrity_errors = _bundle_integrity_errors(contract, bundle)

    claims = {
        "session.binding": _binding_claim(contract, bundle, policy),
        "service.runtime": _runtime_claim(contract, bundle),
        "service.availability": _availability_claim(contract, bundle),
        "service.performance": _performance_claim(contract, bundle, policy),
    }

    fatal_integrity = {
        "DUPLICATE_EVIDENCE_ID",
        "DUPLICATE_SEQUENCE_NUMBER",
    }.intersection(integrity_errors)

    mandatory = [claims[claim_id] for claim_id in contract.mandatory_claims if claim_id in claims]

    if fatal_integrity:
        decision = Decision.REJECT
        reason_codes = tuple(sorted(fatal_integrity))
    elif any(result.state == ClaimState.CONTRADICTING for result in mandatory):
        decision = Decision.REJECT
        reason_codes = tuple(
            sorted(
                {
                    code
                    for result in mandatory
                    if result.state == ClaimState.CONTRADICTING
                    for code in result.reason_codes
                }
            )
        )
    elif any(result.state == ClaimState.INVALID for result in mandatory):
        decision = Decision.REJECT
        reason_codes = tuple(
            sorted(
                {
                    code
                    for result in mandatory
                    if result.state == ClaimState.INVALID
                    for code in result.reason_codes
                }
            )
        )
    elif any(result.state == ClaimState.UNKNOWN for result in mandatory):
        decision = Decision.INCONCLUSIVE
        reason_codes = tuple(
            sorted(
                {
                    code
                    for result in mandatory
                    if result.state == ClaimState.UNKNOWN
                    for code in result.reason_codes
                }
            )
        )
    elif all(result.state == ClaimState.AFFIRMING for result in mandatory):
        decision = Decision.ACCEPT
        reason_codes = ()
    else:
        decision = Decision.INCONCLUSIVE
        reason_codes = ("UNRESOLVED_MANDATORY_CLAIM_STATE",)

    if integrity_errors and not fatal_integrity:
        reason_codes = tuple(sorted(set(reason_codes).union(integrity_errors)))

    return VerifierResult(
        schema_version="verifier-result/0.1",
        contract_id=contract.contract_id,
        session_id=contract.session_id,
        verifier_policy_id=policy.policy_id,
        evidence_bundle_root=bundle.bundle_root,
        claims=claims,
        decision=decision,
        reason_codes=reason_codes,
        verifier_build_id=VERIFIER_BUILD_ID,
        research_mode=contract.research_mode,
    )
