// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {NorthStandardSettlement} from "../src/NorthStandardSettlement.sol";

interface Vm {
    function addr(uint256 privateKey) external returns (address);
    function deal(address account, uint256 newBalance) external;
    function prank(address msgSender) external;
    function warp(uint256 newTimestamp) external;
    function sign(uint256 privateKey, bytes32 digest) external returns (uint8 v, bytes32 r, bytes32 s);
    function expectRevert(bytes4 revertData) external;
}

contract NorthStandardSettlementTest {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    NorthStandardSettlement private settlement;

    uint256 private constant BUYER_KEY = 0xB0B;
    uint256 private constant PROVIDER_KEY = 0xA11CE;
    uint256 private constant VERIFIER_KEY = 0xC0FFEE;
    uint256 private constant ATTACKER_KEY = 0xBAD;

    address private buyer;
    address private provider;
    address private verifier;
    address private attacker;

    bytes32 private agreementId;
    bytes32 private contractHash;
    bytes32 private verifierPolicyHash;
    bytes32 private settlementPolicyHash;
    bytes32 private verifierSetId;
    bytes32 private settlementCommitment;
    bytes32 private evidenceRoot;

    uint128 private constant BUYER_ESCROW = 10 ether;
    uint128 private constant PROVIDER_COLLATERAL = 15 ether;
    uint16 private constant REJECT_PENALTY_BPS = 2_000; // demo-only 20%
    uint64 private constant HOLD_TIMEOUT = 1 days;

    uint64 private notBefore;
    uint64 private verifierDeadline;

    function setUp() public {
        settlement = new NorthStandardSettlement();
        agreementId = keccak256(bytes("agreement-001"));
        contractHash = sha256(bytes("canonical-contract"));
        verifierPolicyHash = sha256(bytes("VERIFIER-v0.1"));
        settlementPolicyHash = sha256(bytes("SETTLEMENT-v0.1"));
        verifierSetId = keccak256(bytes("verifier-set-demo"));
        settlementCommitment = sha256(bytes("canonical-settlement-commitment"));
        evidenceRoot = sha256(bytes("canonical-evidence-bundle"));

        buyer = vm.addr(BUYER_KEY);
        provider = vm.addr(PROVIDER_KEY);
        verifier = vm.addr(VERIFIER_KEY);
        attacker = vm.addr(ATTACKER_KEY);

        vm.deal(buyer, 100 ether);
        vm.deal(provider, 100 ether);
        vm.deal(attacker, 100 ether);

        notBefore = uint64(block.timestamp + 1 hours);
        verifierDeadline = uint64(block.timestamp + 2 days);

        NorthStandardSettlement.AgreementTerms memory terms = NorthStandardSettlement.AgreementTerms({
            provider: provider,
            verifierSigner: verifier,
            contractHash: contractHash,
            verifierPolicyHash: verifierPolicyHash,
            settlementPolicyHash: settlementPolicyHash,
            verifierSetId: verifierSetId,
            providerCollateralRequired: PROVIDER_COLLATERAL,
            rejectPenaltyBps: REJECT_PENALTY_BPS,
            verifierNotBefore: notBefore,
            verifierDeadline: verifierDeadline,
            holdTimeout: HOLD_TIMEOUT
        });

        vm.prank(buyer);
        settlement.createAgreement{value: BUYER_ESCROW}(agreementId, terms);

        vm.prank(provider);
        settlement.fundProviderCollateral{value: PROVIDER_COLLATERAL}(agreementId);
        vm.warp(notBefore + 1);
    }

    function testAcceptCreditsEscrowAndCollateralToProvider() public {
        NorthStandardSettlement.SettlementAuthorization memory authorization = _authorization(
            NorthStandardSettlement.Decision.ACCEPT,
            1
        );
        settlement.submitVerifierResult(authorization, _signVerifier(authorization));

        _requireState(NorthStandardSettlement.SettlementState.SETTLED);
        require(settlement.claimable(provider) == BUYER_ESCROW + PROVIDER_COLLATERAL, "provider credit mismatch");
        require(settlement.claimable(buyer) == 0, "buyer should not be credited on accept");
    }

    function testRejectRefundsBuyerAndAppliesConfiguredPenalty() public {
        NorthStandardSettlement.SettlementAuthorization memory authorization = _authorization(
            NorthStandardSettlement.Decision.REJECT,
            2
        );
        settlement.submitVerifierResult(authorization, _signVerifier(authorization));

        uint256 penalty = (uint256(PROVIDER_COLLATERAL) * REJECT_PENALTY_BPS) / 10_000;
        require(settlement.claimable(buyer) == uint256(BUYER_ESCROW) + penalty, "buyer refund/penalty mismatch");
        require(settlement.claimable(provider) == uint256(PROVIDER_COLLATERAL) - penalty, "provider collateral return mismatch");
        _requireState(NorthStandardSettlement.SettlementState.SETTLED);
    }

    function testInconclusiveMovesToHeldWithoutCreditingFunds() public {
        NorthStandardSettlement.SettlementAuthorization memory authorization = _authorization(
            NorthStandardSettlement.Decision.INCONCLUSIVE,
            3
        );
        settlement.submitVerifierResult(authorization, _signVerifier(authorization));

        _requireState(NorthStandardSettlement.SettlementState.HELD);
        require(settlement.claimable(buyer) == 0, "buyer credited during hold");
        require(settlement.claimable(provider) == 0, "provider credited during hold");

        (, , , , , , , uint128 escrowLocked, , uint128 collateralLocked, , , , , uint64 holdStartedAt, , bool consumed) =
            settlement.agreements(agreementId);
        require(escrowLocked == BUYER_ESCROW, "escrow must remain locked");
        require(collateralLocked == PROVIDER_COLLATERAL, "collateral must remain locked");
        require(holdStartedAt != 0, "hold start missing");
        require(consumed, "result should be consumed");
    }

    function testUnauthorizedVerifierCannotSettle() public {
        NorthStandardSettlement.SettlementAuthorization memory authorization = _authorization(
            NorthStandardSettlement.Decision.ACCEPT,
            4
        );
        bytes32 digest = settlement.authorizationDigest(authorization);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(ATTACKER_KEY, digest);
        bytes memory signature = abi.encodePacked(r, s, v);

        vm.expectRevert(NorthStandardSettlement.UnauthorizedVerifier.selector);
        settlement.submitVerifierResult(authorization, signature);
    }

    function testPolicyMismatchCannotSettle() public {
        NorthStandardSettlement.SettlementAuthorization memory authorization = _authorization(
            NorthStandardSettlement.Decision.ACCEPT,
            5
        );
        authorization.verifierPolicyHash = sha256(bytes("VERIFIER-v9"));

        vm.expectRevert(NorthStandardSettlement.AuthorizationFieldMismatch.selector);
        settlement.submitVerifierResult(authorization, _signRaw(VERIFIER_KEY, settlement.authorizationDigest(authorization)));
    }

    function testExpiredAuthorizationCannotSettle() public {
        NorthStandardSettlement.SettlementAuthorization memory authorization = _authorization(
            NorthStandardSettlement.Decision.ACCEPT,
            6
        );
        authorization.validUntil = uint64(block.timestamp - 1);

        vm.expectRevert(NorthStandardSettlement.AuthorizationExpired.selector);
        settlement.submitVerifierResult(authorization, _signVerifier(authorization));
    }

    function testReplayFailsAfterResultConsumed() public {
        NorthStandardSettlement.SettlementAuthorization memory authorization = _authorization(
            NorthStandardSettlement.Decision.ACCEPT,
            7
        );
        bytes memory signature = _signVerifier(authorization);
        settlement.submitVerifierResult(authorization, signature);

        vm.expectRevert(NorthStandardSettlement.ResultAlreadyConsumed.selector);
        settlement.submitVerifierResult(authorization, signature);
    }

    function testVerifierTimeoutEntersHeldInsteadOfRejectingProvider() public {
        vm.warp(uint256(verifierDeadline) + 1);
        settlement.enterHeldOnVerifierTimeout(agreementId);
        _requireState(NorthStandardSettlement.SettlementState.HELD);
        require(settlement.claimable(buyer) == 0 && settlement.claimable(provider) == 0, "timeout moved funds");
    }

    function testHeldTimeoutPerformsNeutralUnwind() public {
        NorthStandardSettlement.SettlementAuthorization memory authorization = _authorization(
            NorthStandardSettlement.Decision.INCONCLUSIVE,
            8
        );
        settlement.submitVerifierResult(authorization, _signVerifier(authorization));

        (, , , , , , , , , , , , , , uint64 holdStartedAt, , ) = settlement.agreements(agreementId);
        vm.warp(uint256(holdStartedAt) + HOLD_TIMEOUT);
        settlement.resolveHeldAfterTimeout(agreementId);

        require(settlement.claimable(buyer) == BUYER_ESCROW, "buyer escrow not refunded");
        require(settlement.claimable(provider) == PROVIDER_COLLATERAL, "provider collateral not returned");
        _requireState(NorthStandardSettlement.SettlementState.SETTLED);
    }

    function testHeldCanResolveMutuallyWithBothSignatures() public {
        NorthStandardSettlement.SettlementAuthorization memory authorization = _authorization(
            NorthStandardSettlement.Decision.INCONCLUSIVE,
            9
        );
        settlement.submitVerifierResult(authorization, _signVerifier(authorization));

        uint256 buyerAmount = 12 ether;
        uint256 providerAmount = 13 ether;
        NorthStandardSettlement.MutualResolution memory resolution = NorthStandardSettlement.MutualResolution({
            agreementId: agreementId,
            buyerAmount: buyerAmount,
            providerAmount: providerAmount,
            nonce: 1,
            validUntil: uint64(block.timestamp + 1 hours)
        });

        bytes32 digest = settlement.mutualResolutionDigest(resolution);
        settlement.resolveHeldMutually(
            resolution,
            _signRaw(BUYER_KEY, digest),
            _signRaw(PROVIDER_KEY, digest)
        );

        require(settlement.claimable(buyer) == buyerAmount, "mutual buyer allocation mismatch");
        require(settlement.claimable(provider) == providerAmount, "mutual provider allocation mismatch");
        _requireState(NorthStandardSettlement.SettlementState.SETTLED);
    }

    function testWithdrawalUsesPullPayment() public {
        NorthStandardSettlement.SettlementAuthorization memory authorization = _authorization(
            NorthStandardSettlement.Decision.ACCEPT,
            10
        );
        settlement.submitVerifierResult(authorization, _signVerifier(authorization));

        uint256 beforeBalance = provider.balance;
        vm.prank(provider);
        settlement.withdraw();
        require(provider.balance == beforeBalance + BUYER_ESCROW + PROVIDER_COLLATERAL, "withdrawal mismatch");
        require(settlement.claimable(provider) == 0, "claimable not cleared");
    }

    function _authorization(
        NorthStandardSettlement.Decision decision,
        uint256 nonce
    ) private view returns (NorthStandardSettlement.SettlementAuthorization memory) {
        return NorthStandardSettlement.SettlementAuthorization({
            agreementId: agreementId,
            contractHash: contractHash,
            settlementCommitment: settlementCommitment,
            evidenceBundleRoot: evidenceRoot,
            verifierPolicyHash: verifierPolicyHash,
            settlementPolicyHash: settlementPolicyHash,
            verifierSetId: verifierSetId,
            decision: decision,
            issuedAt: uint64(block.timestamp),
            validUntil: uint64(block.timestamp + 1 hours),
            nonce: nonce
        });
    }

    function _signVerifier(
        NorthStandardSettlement.SettlementAuthorization memory authorization
    ) private returns (bytes memory) {
        return _signRaw(VERIFIER_KEY, settlement.authorizationDigest(authorization));
    }

    function _signRaw(uint256 key, bytes32 digest) private returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, digest);
        return abi.encodePacked(r, s, v);
    }

    function _requireState(NorthStandardSettlement.SettlementState expected) private view {
        (, , , , , , , , , , , , , , , NorthStandardSettlement.SettlementState state, ) =
            settlement.agreements(agreementId);
        require(state == expected, "unexpected state");
    }
}
