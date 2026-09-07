"""Deterministic synthetic scenarios for the Step-1 vertical verifier slice."""

from __future__ import annotations

from enum import Enum

from .models import ComputeContract, EvidenceBundle, EvidenceRecord, EvidenceType


class Scenario(str, Enum):
    HEALTHY_SERVICE = "healthy_service"
    REPLAYED_EVIDENCE = "replayed_evidence"
    CONSTANT_THROTTLE = "constant_throttle"
    AMBIGUOUS_NETWORK_FAILURE = "ambiguous_network_failure"


def demo_contract(contract_id: str = "contract-001", session_id: str = "session-001") -> ComputeContract:
    """Create a research-mode contract fixture.

    The performance floor is deliberately marked as experiment-defined by research_mode;
    it is not a production recommendation or measured H100 threshold.
    """

    return ComputeContract(
        schema_version="compute-contract/0.1",
        contract_id=contract_id,
        contract_class_id="TEST-NVIDIA-GPU-PROFILE-v0.1",
        provider_id="provider-demo",
        buyer_id="buyer-demo",
        session_id=session_id,
        runtime_profile_id="CUDA-TEST-RUNTIME-v0.1",
        delivery_start=1_800_000_000,
        duration_seconds=600,
        sla_policy_id="SLA-v0.1",
        benchmark_profile_id="GPU-SERVICE-CHALLENGE-v0.1",
        performance_min_score=0.80,
        verifier_policy_id="VERIFIER-v0.1",
        settlement_policy_id="SETTLEMENT-v0.1",
        research_mode=True,
    )


def _record(
    contract: ComputeContract,
    evidence_id: str,
    evidence_type: EvidenceType,
    sequence_number: int,
    payload: dict,
    *,
    session_id: str | None = None,
    producer_id: str = "verifier-fixture",
    nonce: str | None = None,
) -> EvidenceRecord:
    observed = contract.delivery_start + min(sequence_number * 10, contract.duration_seconds - 1)
    return EvidenceRecord(
        schema_version="evidence/0.1",
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        producer_id=producer_id,
        contract_id=contract.contract_id,
        session_id=session_id or contract.session_id,
        observed_at=observed,
        received_at=observed + 1,
        sequence_number=sequence_number,
        payload=payload,
        nonce=nonce or f"nonce-{evidence_id}",
        authentication_valid=True,
        trust_tier="T4" if evidence_type == EvidenceType.EXTERNAL_PROBE else "T1",
    )


def _healthy_records(contract: ComputeContract) -> list[EvidenceRecord]:
    return [
        _record(
            contract,
            "bind-1",
            EvidenceType.SESSION_BINDING,
            1,
            {"bound": True},
            producer_id="provider-session-key",
        ),
        _record(
            contract,
            "runtime-1",
            EvidenceType.RUNTIME_CHECK,
            2,
            {"usable": True, "runtime_profile_id": contract.runtime_profile_id},
        ),
        _record(
            contract,
            "telemetry-1",
            EvidenceType.TELEMETRY,
            3,
            {"service_state": "HEALTHY"},
            producer_id="provider-agent",
        ),
        _record(
            contract,
            "challenge-1",
            EvidenceType.CHALLENGE,
            4,
            {"score": 0.96, "timed_out": False},
        ),
        _record(
            contract,
            "challenge-2",
            EvidenceType.CHALLENGE,
            5,
            {"score": 1.01, "timed_out": False},
        ),
        _record(
            contract,
            "challenge-3",
            EvidenceType.CHALLENGE,
            6,
            {"score": 0.93, "timed_out": False},
        ),
        _record(
            contract,
            "probe-1",
            EvidenceType.EXTERNAL_PROBE,
            7,
            {"result": "SUCCESS", "attribution": "NONE"},
            producer_id="independent-probe-a",
        ),
    ]


def simulate_scenario(
    scenario: Scenario | str,
    contract: ComputeContract | None = None,
) -> tuple[ComputeContract, EvidenceBundle]:
    contract = contract or demo_contract()
    scenario = Scenario(scenario)
    records = _healthy_records(contract)

    if scenario == Scenario.REPLAYED_EVIDENCE:
        records[0] = _record(
            contract,
            "bind-replayed",
            EvidenceType.SESSION_BINDING,
            1,
            {"bound": True, "source": "old-session"},
            session_id="session-from-another-contract",
            producer_id="provider-session-key",
        )

    elif scenario == Scenario.CONSTANT_THROTTLE:
        records = [r for r in records if r.evidence_type != EvidenceType.CHALLENGE]
        for idx, score in enumerate((0.56, 0.58, 0.55), start=4):
            records.append(
                _record(
                    contract,
                    f"challenge-throttle-{idx}",
                    EvidenceType.CHALLENGE,
                    idx,
                    {"score": score, "timed_out": False},
                )
            )

    elif scenario == Scenario.AMBIGUOUS_NETWORK_FAILURE:
        records = [r for r in records if r.evidence_type != EvidenceType.EXTERNAL_PROBE]
        records.append(
            _record(
                contract,
                "probe-ambiguous",
                EvidenceType.EXTERNAL_PROBE,
                7,
                {"result": "FAILURE", "attribution": "UNKNOWN", "error": "path timeout"},
                producer_id="buyer-edge-probe",
            )
        )

    records = sorted(records, key=lambda r: (r.observed_at, r.evidence_id))
    bundle = EvidenceBundle(
        contract_id=contract.contract_id,
        session_id=contract.session_id,
        records=tuple(records),
    )
    return contract, bundle
