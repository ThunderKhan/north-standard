"""Build the signer-facing authorization package for Monad settlement.

This module deliberately does not hold or use private keys. The verifier produces a
settlement commitment; this layer binds that commitment to an onchain agreement and
emits standard EIP-712 typed data for an external wallet/HSM/signer.
"""

from __future__ import annotations

from hashlib import sha256
import re
from typing import Any

from .commitment import settlement_hash
from .models import ComputeContract, Decision, VerifierResult

_DECISION_TO_UINT8 = {
    Decision.ACCEPT: 0,
    Decision.REJECT: 1,
    Decision.INCONCLUSIVE: 2,
}
_HEX32_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _require_hex32(value: str, name: str) -> str:
    if not _HEX32_RE.fullmatch(value):
        raise ValueError(f"{name} must be a 0x-prefixed bytes32 hex string")
    return value.lower()


def _require_address(value: str) -> str:
    if not _ADDRESS_RE.fullmatch(value):
        raise ValueError("verifying_contract must be a 20-byte 0x-prefixed address")
    return value.lower()


def _prefixed_sha256_hex(raw_hex: str) -> str:
    if len(raw_hex) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in raw_hex):
        raise ValueError("expected a 32-byte SHA-256 hex digest")
    return "0x" + raw_hex.lower()


def _sha256_text(value: str) -> str:
    return "0x" + sha256(value.encode("utf-8")).hexdigest()


def build_settlement_authorization(
    contract: ComputeContract,
    result: VerifierResult,
    *,
    agreement_id: str,
    verifier_set_id: str,
    issued_at: int,
    valid_until: int,
    nonce: int,
) -> dict[str, Any]:
    """Build settlement-authorization/0.1 without performing any signing."""

    if result.contract_id != contract.contract_id:
        raise ValueError("verifier result does not belong to the supplied contract")
    if result.verifier_policy_id != contract.verifier_policy_id:
        raise ValueError("verifier result policy does not match contract policy")
    if issued_at < 0 or valid_until < 0 or nonce < 0:
        raise ValueError("issued_at, valid_until, and nonce must be non-negative")
    if valid_until < issued_at:
        raise ValueError("valid_until must not precede issued_at")

    return {
        "schema_version": "settlement-authorization/0.1",
        "agreement_id": _require_hex32(agreement_id, "agreement_id"),
        "contract_hash": _prefixed_sha256_hex(contract.semantic_hash),
        "settlement_commitment": _prefixed_sha256_hex(settlement_hash(result)),
        "evidence_bundle_root": _prefixed_sha256_hex(result.evidence_bundle_root),
        "verifier_policy_hash": _sha256_text(result.verifier_policy_id),
        "settlement_policy_hash": _sha256_text(contract.settlement_policy_id),
        "verifier_set_id": _require_hex32(verifier_set_id, "verifier_set_id"),
        "decision": result.decision.value,
        "issued_at": issued_at,
        "valid_until": valid_until,
        "nonce": nonce,
    }


def eip712_typed_data(
    authorization: dict[str, Any],
    *,
    chain_id: int,
    verifying_contract: str,
) -> dict[str, Any]:
    """Convert settlement-authorization/0.1 to the contract's EIP-712 shape."""

    if chain_id <= 0:
        raise ValueError("chain_id must be positive")
    decision = Decision(authorization["decision"])

    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "SettlementAuthorization": [
                {"name": "agreementId", "type": "bytes32"},
                {"name": "contractHash", "type": "bytes32"},
                {"name": "settlementCommitment", "type": "bytes32"},
                {"name": "evidenceBundleRoot", "type": "bytes32"},
                {"name": "verifierPolicyHash", "type": "bytes32"},
                {"name": "settlementPolicyHash", "type": "bytes32"},
                {"name": "verifierSetId", "type": "bytes32"},
                {"name": "decision", "type": "uint8"},
                {"name": "issuedAt", "type": "uint64"},
                {"name": "validUntil", "type": "uint64"},
                {"name": "nonce", "type": "uint256"},
            ],
        },
        "primaryType": "SettlementAuthorization",
        "domain": {
            "name": "North Standard Settlement",
            "version": "0.1",
            "chainId": chain_id,
            "verifyingContract": _require_address(verifying_contract),
        },
        "message": {
            "agreementId": authorization["agreement_id"],
            "contractHash": authorization["contract_hash"],
            "settlementCommitment": authorization["settlement_commitment"],
            "evidenceBundleRoot": authorization["evidence_bundle_root"],
            "verifierPolicyHash": authorization["verifier_policy_hash"],
            "settlementPolicyHash": authorization["settlement_policy_hash"],
            "verifierSetId": authorization["verifier_set_id"],
            "decision": _DECISION_TO_UINT8[decision],
            "issuedAt": authorization["issued_at"],
            "validUntil": authorization["valid_until"],
            "nonce": authorization["nonce"],
        },
    }


def signing_package(
    contract: ComputeContract,
    result: VerifierResult,
    *,
    agreement_id: str,
    verifier_set_id: str,
    issued_at: int,
    valid_until: int,
    nonce: int,
    chain_id: int,
    verifying_contract: str,
) -> dict[str, Any]:
    """Return the unsigned authorization and wallet/HSM-facing typed data together."""

    authorization = build_settlement_authorization(
        contract,
        result,
        agreement_id=agreement_id,
        verifier_set_id=verifier_set_id,
        issued_at=issued_at,
        valid_until=valid_until,
        nonce=nonce,
    )
    return {
        "authorization": authorization,
        "eip712_typed_data": eip712_typed_data(
            authorization,
            chain_id=chain_id,
            verifying_contract=verifying_contract,
        ),
    }
