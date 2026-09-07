"""Language-neutral settlement commitment for verifier outcomes.

The full verifier result contains implementation-specific audit metadata and diagnostic
metrics. Settlement commits only to the policy-bound semantic outcome and evidence root.
"""

from __future__ import annotations

from typing import Any

from .canonical import canonical_sha256
from .models import VerifierResult


def settlement_payload(result: VerifierResult) -> dict[str, Any]:
    """Return the compact v0.1 settlement-critical semantic payload."""

    return {
        "schema_version": "settlement-commitment/0.1",
        "contract_id": result.contract_id,
        "session_id": result.session_id,
        "verifier_policy_id": result.verifier_policy_id,
        "evidence_bundle_root": result.evidence_bundle_root,
        "claims": {
            claim_id: {
                "state": claim.state.value,
                "reason_codes": list(claim.reason_codes),
            }
            for claim_id, claim in sorted(result.claims.items())
        },
        "overall": {
            "decision": result.decision.value,
            "reason_codes": list(result.reason_codes),
        },
    }


def settlement_hash(result: VerifierResult) -> str:
    """Return the SHA-256 commitment consumed by the next settlement milestone."""

    return canonical_sha256(settlement_payload(result))
