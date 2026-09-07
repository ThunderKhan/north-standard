// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {NorthStandardSettlement} from "../src/NorthStandardSettlement.sol";
import {GeneratedVerifierSettlementFixtures as Fixture} from "./generated/GeneratedVerifierSettlementFixtures.sol";

interface VmE2E {
    function addr(uint256 privateKey) external returns (address);
    function deal(address account, uint256 newBalance) external;
    function prank(address msgSender) external;
    function warp(uint256 newTimestamp) external;
    function sign(uint256 privateKey, bytes32 digest) external returns (uint8 v, bytes32 r, bytes32 s);
}

/// @notice Cross-layer proof: verifier-produced hashes become signed authorizations that move escrow.
contract VerifierSettlementE2ETest {
    VmE2E private constant vm = VmE2E(address(uint160(uint256(keccak256("hevm cheat code")))));

    uint256 private constant BUYER_KEY = 0xB0B;
    uint256 private constant PROVIDER_KEY = 0xA11CE;
    uint256 private constant VERIFIER_KEY = 0xC0FFEE;

    uint128 private constant BUYER_ESCROW = 1 ether;
    uint128 private constant PROVIDER_COLLATERAL = 2 ether;
    uint16 private constant REJECT_PENALTY_BPS = 2_000;
    uint64 private constant HOLD_TIMEOUT = 1 days;

    NorthStandardSettlement private settlement;
    address private buyer;
    address private provider;
    address private verifier;

    function setUp() public {
        settlement = new NorthStandardSettlement();
        buyer = vm.addr(BUYER_KEY);
        provider = vm.addr(PROVIDER_KEY);
        verifier = vm.addr(VERIFIER_KEY);
        vm.deal(buyer, 100 ether);
        vm.deal(provider, 100 ether);
    }

    function testHealthyVerifierOutputPaysProvider() public {
        _submit(
            Fixture.HEALTHY_AGREEMENT_ID,
            Fixture.HEALTHY_SETTLEMENT_COMMITMENT,
            Fixture.HEALTHY_EVIDENCE_BUNDLE_ROOT,
            Fixture.HEALTHY_DECISION,
            Fixture.HEALTHY_NONCE
        );

        require(Fixture.HEALTHY_DECISION == uint8(NorthStandardSettlement.Decision.ACCEPT), "fixture decision drift");
        require(settlement.claimable(provider) == BUYER_ESCROW + PROVIDER_COLLATERAL, "provider not paid");
        require(settlement.claimable(buyer) == 0, "buyer credited on accept");
        require(_state(Fixture.HEALTHY_AGREEMENT_ID) == NorthStandardSettlement.SettlementState.SETTLED, "not settled");
    }

    function testReplayedEvidenceVerifierOutputRejects() public {
        _submit(
            Fixture.REPLAYED_AGREEMENT_ID,
            Fixture.REPLAYED_SETTLEMENT_COMMITMENT,
            Fixture.REPLAYED_EVIDENCE_BUNDLE_ROOT,
            Fixture.REPLAYED_DECISION,
            Fixture.REPLAYED_NONCE
        );
        _assertRejectCredits(Fixture.REPLAYED_AGREEMENT_ID, Fixture.REPLAYED_DECISION);
    }

    function testConstantThrottleVerifierOutputRejects() public {
        _submit(
            Fixture.THROTTLE_AGREEMENT_ID,
            Fixture.THROTTLE_SETTLEMENT_COMMITMENT,
            Fixture.THROTTLE_EVIDENCE_BUNDLE_ROOT,
            Fixture.THROTTLE_DECISION,
            Fixture.THROTTLE_NONCE
        );
        _assertRejectCredits(Fixture.THROTTLE_AGREEMENT_ID, Fixture.THROTTLE_DECISION);
    }

    function testAmbiguousNetworkFailureVerifierOutputHoldsFunds() public {
        _submit(
            Fixture.AMBIGUOUS_AGREEMENT_ID,
            Fixture.AMBIGUOUS_SETTLEMENT_COMMITMENT,
            Fixture.AMBIGUOUS_EVIDENCE_BUNDLE_ROOT,
            Fixture.AMBIGUOUS_DECISION,
            Fixture.AMBIGUOUS_NONCE
        );

        require(Fixture.AMBIGUOUS_DECISION == uint8(NorthStandardSettlement.Decision.INCONCLUSIVE), "fixture decision drift");
        require(settlement.claimable(buyer) == 0, "buyer credited during hold");
        require(settlement.claimable(provider) == 0, "provider credited during hold");
        require(_state(Fixture.AMBIGUOUS_AGREEMENT_ID) == NorthStandardSettlement.SettlementState.HELD, "not held");
    }

    function _submit(
        bytes32 agreementId,
        bytes32 settlementCommitment,
        bytes32 evidenceBundleRoot,
        uint8 decision,
        uint256 nonce
    ) private {
        vm.warp(uint256(Fixture.ISSUED_AT) - 100);
        NorthStandardSettlement.AgreementTerms memory terms = NorthStandardSettlement.AgreementTerms({
            provider: provider,
            verifierSigner: verifier,
            contractHash: Fixture.CONTRACT_HASH,
            verifierPolicyHash: Fixture.VERIFIER_POLICY_HASH,
            settlementPolicyHash: Fixture.SETTLEMENT_POLICY_HASH,
            verifierSetId: Fixture.VERIFIER_SET_ID,
            providerCollateralRequired: PROVIDER_COLLATERAL,
            rejectPenaltyBps: REJECT_PENALTY_BPS,
            verifierNotBefore: Fixture.ISSUED_AT - 10,
            verifierDeadline: Fixture.VALID_UNTIL + 100,
            holdTimeout: HOLD_TIMEOUT
        });

        vm.prank(buyer);
        settlement.createAgreement{value: BUYER_ESCROW}(agreementId, terms);
        vm.prank(provider);
        settlement.fundProviderCollateral{value: PROVIDER_COLLATERAL}(agreementId);

        vm.warp(Fixture.ISSUED_AT);
        NorthStandardSettlement.SettlementAuthorization memory authorization =
            NorthStandardSettlement.SettlementAuthorization({
                agreementId: agreementId,
                contractHash: Fixture.CONTRACT_HASH,
                settlementCommitment: settlementCommitment,
                evidenceBundleRoot: evidenceBundleRoot,
                verifierPolicyHash: Fixture.VERIFIER_POLICY_HASH,
                settlementPolicyHash: Fixture.SETTLEMENT_POLICY_HASH,
                verifierSetId: Fixture.VERIFIER_SET_ID,
                decision: NorthStandardSettlement.Decision(decision),
                issuedAt: Fixture.ISSUED_AT,
                validUntil: Fixture.VALID_UNTIL,
                nonce: nonce
            });

        bytes32 digest = settlement.authorizationDigest(authorization);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(VERIFIER_KEY, digest);
        settlement.submitVerifierResult(authorization, abi.encodePacked(r, s, v));
    }

    function _assertRejectCredits(bytes32 agreementId, uint8 fixtureDecision) private view {
        require(fixtureDecision == uint8(NorthStandardSettlement.Decision.REJECT), "fixture decision drift");
        uint256 penalty = (uint256(PROVIDER_COLLATERAL) * REJECT_PENALTY_BPS) / 10_000;
        require(settlement.claimable(buyer) == uint256(BUYER_ESCROW) + penalty, "buyer reject credit mismatch");
        require(settlement.claimable(provider) == uint256(PROVIDER_COLLATERAL) - penalty, "provider reject credit mismatch");
        require(_state(agreementId) == NorthStandardSettlement.SettlementState.SETTLED, "reject not settled");
    }

    function _state(bytes32 agreementId) private view returns (NorthStandardSettlement.SettlementState state) {
        (, , , , , , , , , , , , , , , state, ) = settlement.agreements(agreementId);
    }
}
