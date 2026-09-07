// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

library NorthStandardECDSA {
    error InvalidSignatureLength();
    error InvalidSignatureS();
    error InvalidSignatureV();
    error InvalidSignature();

    // secp256k1n / 2
    uint256 private constant _HALF_ORDER =
        0x7fffffffffffffffffffffffffffffff5d576e7357a4501ddfe92f46681b20a0;

    function recover(bytes32 digest, bytes calldata signature) internal pure returns (address signer) {
        if (signature.length != 65) revert InvalidSignatureLength();

        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly ("memory-safe") {
            r := calldataload(signature.offset)
            s := calldataload(add(signature.offset, 0x20))
            v := byte(0, calldataload(add(signature.offset, 0x40)))
        }

        if (uint256(s) > _HALF_ORDER) revert InvalidSignatureS();
        if (v != 27 && v != 28) revert InvalidSignatureV();

        signer = ecrecover(digest, v, r, s);
        if (signer == address(0)) revert InvalidSignature();
    }
}

/// @title North Standard Settlement
/// @notice Experimental escrow/collateral settlement for contract-bound GPU service.
/// @dev Raw evidence and telemetry never move funds. Only an authorized verifier result does.
contract NorthStandardSettlement {
    using NorthStandardECDSA for bytes32;

    enum SettlementState {
        NONE,
        FUNDED,
        ACTIVE,
        HELD,
        SETTLED,
        CANCELLED
    }

    enum Decision {
        ACCEPT,
        REJECT,
        INCONCLUSIVE
    }

    struct AgreementTerms {
        address provider;
        address verifierSigner;
        bytes32 contractHash;
        bytes32 verifierPolicyHash;
        bytes32 settlementPolicyHash;
        bytes32 verifierSetId;
        uint128 providerCollateralRequired;
        uint16 rejectPenaltyBps;
        uint64 verifierNotBefore;
        uint64 verifierDeadline;
        uint64 holdTimeout;
    }

    struct Agreement {
        address buyer;
        address provider;
        address verifierSigner;
        bytes32 contractHash;
        bytes32 verifierPolicyHash;
        bytes32 settlementPolicyHash;
        bytes32 verifierSetId;
        uint128 buyerEscrowLocked;
        uint128 providerCollateralRequired;
        uint128 providerCollateralLocked;
        uint16 rejectPenaltyBps;
        uint64 verifierNotBefore;
        uint64 verifierDeadline;
        uint64 holdTimeout;
        uint64 holdStartedAt;
        SettlementState state;
        bool resultConsumed;
    }

    struct SettlementAuthorization {
        bytes32 agreementId;
        bytes32 contractHash;
        bytes32 settlementCommitment;
        bytes32 evidenceBundleRoot;
        bytes32 verifierPolicyHash;
        bytes32 settlementPolicyHash;
        bytes32 verifierSetId;
        Decision decision;
        uint64 issuedAt;
        uint64 validUntil;
        uint256 nonce;
    }

    struct MutualResolution {
        bytes32 agreementId;
        uint256 buyerAmount;
        uint256 providerAmount;
        uint256 nonce;
        uint64 validUntil;
    }

    error ZeroAddress();
    error InvalidAgreementId();
    error AgreementAlreadyExists();
    error AgreementNotFound();
    error InvalidState(SettlementState expected, SettlementState actual);
    error NotBuyer();
    error NotProvider();
    error IncorrectValue(uint256 expected, uint256 actual);
    error AmountTooLarge();
    error InvalidTiming();
    error InvalidPenaltyBps();
    error ResultAlreadyConsumed();
    error AuthorizationTooEarly();
    error AuthorizationWindowClosed();
    error AuthorizationExpired();
    error AuthorizationFromFuture();
    error AuthorizationFieldMismatch();
    error EmptySettlementCommitment();
    error EmptyEvidenceBundleRoot();
    error UnauthorizedVerifier(address recovered);
    error AuthorizationNonceUsed();
    error HoldTimeoutNotReached();
    error ResolutionExpired();
    error ResolutionAmountMismatch();
    error ResolutionNonceUsed();
    error InvalidBuyerSignature(address recovered);
    error InvalidProviderSignature(address recovered);
    error NothingToWithdraw();
    error NativeTransferFailed();
    error Reentrancy();

    event AgreementCreated(
        bytes32 indexed agreementId,
        address indexed buyer,
        address indexed provider,
        bytes32 contractHash,
        uint256 buyerEscrow,
        uint256 providerCollateralRequired
    );
    event ProviderCollateralFunded(bytes32 indexed agreementId, uint256 amount);
    event AgreementActivated(bytes32 indexed agreementId);
    event AgreementCancelled(bytes32 indexed agreementId);
    event VerifierResultAccepted(
        bytes32 indexed agreementId,
        bytes32 indexed settlementCommitment,
        bytes32 indexed evidenceBundleRoot,
        Decision decision,
        address verifierSigner,
        uint256 nonce
    );
    event AgreementHeld(bytes32 indexed agreementId, uint64 holdStartedAt, string reason);
    event AgreementSettled(
        bytes32 indexed agreementId,
        Decision decision,
        uint256 buyerCredit,
        uint256 providerCredit
    );
    event MutualResolutionApplied(
        bytes32 indexed agreementId,
        uint256 buyerAmount,
        uint256 providerAmount,
        uint256 nonce
    );
    event TimeoutResolutionApplied(bytes32 indexed agreementId, uint256 buyerAmount, uint256 providerAmount);
    event Withdrawal(address indexed account, uint256 amount);

    string public constant NAME = "North Standard Settlement";
    string public constant VERSION = "0.1";

    bytes32 public constant SETTLEMENT_AUTHORIZATION_TYPEHASH = keccak256(
        "SettlementAuthorization(bytes32 agreementId,bytes32 contractHash,bytes32 settlementCommitment,bytes32 evidenceBundleRoot,bytes32 verifierPolicyHash,bytes32 settlementPolicyHash,bytes32 verifierSetId,uint8 decision,uint64 issuedAt,uint64 validUntil,uint256 nonce)"
    );

    bytes32 public constant MUTUAL_RESOLUTION_TYPEHASH = keccak256(
        "MutualResolution(bytes32 agreementId,uint256 buyerAmount,uint256 providerAmount,uint256 nonce,uint64 validUntil)"
    );

    bytes32 private constant _EIP712_DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 private constant _NAME_HASH = keccak256(bytes(NAME));
    bytes32 private constant _VERSION_HASH = keccak256(bytes(VERSION));

    mapping(bytes32 => Agreement) public agreements;
    mapping(address => uint256) public claimable;
    mapping(address => mapping(uint256 => bool)) public verifierNonceUsed;
    mapping(bytes32 => mapping(uint256 => bool)) public resolutionNonceUsed;

    uint256 private _reentrancyLock = 1;

    modifier nonReentrant() {
        if (_reentrancyLock != 1) revert Reentrancy();
        _reentrancyLock = 2;
        _;
        _reentrancyLock = 1;
    }

    function domainSeparator() public view returns (bytes32) {
        return keccak256(
            abi.encode(
                _EIP712_DOMAIN_TYPEHASH,
                _NAME_HASH,
                _VERSION_HASH,
                block.chainid,
                address(this)
            )
        );
    }

    function createAgreement(bytes32 agreementId, AgreementTerms calldata terms) external payable {
        if (agreementId == bytes32(0)) revert InvalidAgreementId();
        if (terms.provider == address(0) || terms.verifierSigner == address(0)) revert ZeroAddress();
        if (
            terms.contractHash == bytes32(0) ||
            terms.verifierPolicyHash == bytes32(0) ||
            terms.settlementPolicyHash == bytes32(0)
        ) {
            revert AuthorizationFieldMismatch();
        }
        if (agreements[agreementId].state != SettlementState.NONE) revert AgreementAlreadyExists();
        if (msg.value == 0 || msg.value > type(uint128).max) revert AmountTooLarge();
        if (terms.providerCollateralRequired == 0) revert IncorrectValue(1, 0);
        if (terms.rejectPenaltyBps > 10_000) revert InvalidPenaltyBps();
        if (terms.verifierNotBefore >= terms.verifierDeadline || terms.holdTimeout == 0) revert InvalidTiming();

        agreements[agreementId] = Agreement({
            buyer: msg.sender,
            provider: terms.provider,
            verifierSigner: terms.verifierSigner,
            contractHash: terms.contractHash,
            verifierPolicyHash: terms.verifierPolicyHash,
            settlementPolicyHash: terms.settlementPolicyHash,
            verifierSetId: terms.verifierSetId,
            buyerEscrowLocked: uint128(msg.value),
            providerCollateralRequired: terms.providerCollateralRequired,
            providerCollateralLocked: 0,
            rejectPenaltyBps: terms.rejectPenaltyBps,
            verifierNotBefore: terms.verifierNotBefore,
            verifierDeadline: terms.verifierDeadline,
            holdTimeout: terms.holdTimeout,
            holdStartedAt: 0,
            state: SettlementState.FUNDED,
            resultConsumed: false
        });

        emit AgreementCreated(
            agreementId,
            msg.sender,
            terms.provider,
            terms.contractHash,
            msg.value,
            terms.providerCollateralRequired
        );
    }

    function fundProviderCollateral(bytes32 agreementId) external payable {
        Agreement storage agreement = _agreement(agreementId);
        _requireState(agreement, SettlementState.FUNDED);
        if (msg.sender != agreement.provider) revert NotProvider();
        if (msg.value != agreement.providerCollateralRequired) {
            revert IncorrectValue(agreement.providerCollateralRequired, msg.value);
        }

        agreement.providerCollateralLocked = uint128(msg.value);
        agreement.state = SettlementState.ACTIVE;

        emit ProviderCollateralFunded(agreementId, msg.value);
        emit AgreementActivated(agreementId);
    }

    function cancelBeforeActivation(bytes32 agreementId) external {
        Agreement storage agreement = _agreement(agreementId);
        _requireState(agreement, SettlementState.FUNDED);
        if (msg.sender != agreement.buyer) revert NotBuyer();

        uint256 buyerAmount = agreement.buyerEscrowLocked;
        agreement.buyerEscrowLocked = 0;
        agreement.state = SettlementState.CANCELLED;
        claimable[agreement.buyer] += buyerAmount;

        emit AgreementCancelled(agreementId);
    }

    function authorizationDigest(SettlementAuthorization calldata authorization) public view returns (bytes32) {
        bytes32 structHash = keccak256(
            abi.encode(
                SETTLEMENT_AUTHORIZATION_TYPEHASH,
                authorization.agreementId,
                authorization.contractHash,
                authorization.settlementCommitment,
                authorization.evidenceBundleRoot,
                authorization.verifierPolicyHash,
                authorization.settlementPolicyHash,
                authorization.verifierSetId,
                uint8(authorization.decision),
                authorization.issuedAt,
                authorization.validUntil,
                authorization.nonce
            )
        );
        return keccak256(abi.encodePacked("\x19\x01", domainSeparator(), structHash));
    }

    function submitVerifierResult(
        SettlementAuthorization calldata authorization,
        bytes calldata signature
    ) external {
        Agreement storage agreement = _agreement(authorization.agreementId);
        if (agreement.resultConsumed) revert ResultAlreadyConsumed();
        _requireState(agreement, SettlementState.ACTIVE);

        if (block.timestamp < agreement.verifierNotBefore) revert AuthorizationTooEarly();
        if (block.timestamp > agreement.verifierDeadline) revert AuthorizationWindowClosed();
        if (authorization.issuedAt > block.timestamp) revert AuthorizationFromFuture();
        if (authorization.issuedAt < agreement.verifierNotBefore) revert AuthorizationTooEarly();
        if (authorization.validUntil < block.timestamp) revert AuthorizationExpired();
        if (authorization.settlementCommitment == bytes32(0)) revert EmptySettlementCommitment();
        if (authorization.evidenceBundleRoot == bytes32(0)) revert EmptyEvidenceBundleRoot();

        if (
            authorization.contractHash != agreement.contractHash ||
            authorization.verifierPolicyHash != agreement.verifierPolicyHash ||
            authorization.settlementPolicyHash != agreement.settlementPolicyHash ||
            authorization.verifierSetId != agreement.verifierSetId
        ) {
            revert AuthorizationFieldMismatch();
        }

        if (verifierNonceUsed[agreement.verifierSigner][authorization.nonce]) revert AuthorizationNonceUsed();

        bytes32 digest = authorizationDigest(authorization);
        address recovered = digest.recover(signature);
        if (recovered != agreement.verifierSigner) revert UnauthorizedVerifier(recovered);

        agreement.resultConsumed = true;
        verifierNonceUsed[agreement.verifierSigner][authorization.nonce] = true;

        emit VerifierResultAccepted(
            authorization.agreementId,
            authorization.settlementCommitment,
            authorization.evidenceBundleRoot,
            authorization.decision,
            recovered,
            authorization.nonce
        );

        if (authorization.decision == Decision.ACCEPT) {
            _settleAccept(authorization.agreementId, agreement);
        } else if (authorization.decision == Decision.REJECT) {
            _settleReject(authorization.agreementId, agreement);
        } else {
            agreement.state = SettlementState.HELD;
            agreement.holdStartedAt = uint64(block.timestamp);
            emit AgreementHeld(authorization.agreementId, agreement.holdStartedAt, "INCONCLUSIVE");
        }
    }

    function enterHeldOnVerifierTimeout(bytes32 agreementId) external {
        Agreement storage agreement = _agreement(agreementId);
        _requireState(agreement, SettlementState.ACTIVE);
        if (block.timestamp <= agreement.verifierDeadline) revert AuthorizationWindowClosed();

        agreement.state = SettlementState.HELD;
        agreement.holdStartedAt = uint64(block.timestamp);
        emit AgreementHeld(agreementId, agreement.holdStartedAt, "VERIFIER_TIMEOUT");
    }

    function mutualResolutionDigest(MutualResolution calldata resolution) public view returns (bytes32) {
        bytes32 structHash = keccak256(
            abi.encode(
                MUTUAL_RESOLUTION_TYPEHASH,
                resolution.agreementId,
                resolution.buyerAmount,
                resolution.providerAmount,
                resolution.nonce,
                resolution.validUntil
            )
        );
        return keccak256(abi.encodePacked("\x19\x01", domainSeparator(), structHash));
    }

    function resolveHeldMutually(
        MutualResolution calldata resolution,
        bytes calldata buyerSignature,
        bytes calldata providerSignature
    ) external {
        Agreement storage agreement = _agreement(resolution.agreementId);
        _requireState(agreement, SettlementState.HELD);
        if (resolution.validUntil < block.timestamp) revert ResolutionExpired();
        if (resolutionNonceUsed[resolution.agreementId][resolution.nonce]) revert ResolutionNonceUsed();

        uint256 totalLocked = uint256(agreement.buyerEscrowLocked) + uint256(agreement.providerCollateralLocked);
        if (resolution.buyerAmount + resolution.providerAmount != totalLocked) {
            revert ResolutionAmountMismatch();
        }

        bytes32 digest = mutualResolutionDigest(resolution);
        address buyerRecovered = digest.recover(buyerSignature);
        address providerRecovered = digest.recover(providerSignature);
        if (buyerRecovered != agreement.buyer) revert InvalidBuyerSignature(buyerRecovered);
        if (providerRecovered != agreement.provider) revert InvalidProviderSignature(providerRecovered);

        resolutionNonceUsed[resolution.agreementId][resolution.nonce] = true;
        agreement.buyerEscrowLocked = 0;
        agreement.providerCollateralLocked = 0;
        agreement.state = SettlementState.SETTLED;

        claimable[agreement.buyer] += resolution.buyerAmount;
        claimable[agreement.provider] += resolution.providerAmount;

        emit MutualResolutionApplied(
            resolution.agreementId,
            resolution.buyerAmount,
            resolution.providerAmount,
            resolution.nonce
        );
    }

    function resolveHeldAfterTimeout(bytes32 agreementId) external {
        Agreement storage agreement = _agreement(agreementId);
        _requireState(agreement, SettlementState.HELD);
        if (block.timestamp < uint256(agreement.holdStartedAt) + agreement.holdTimeout) {
            revert HoldTimeoutNotReached();
        }

        uint256 buyerAmount = agreement.buyerEscrowLocked;
        uint256 providerAmount = agreement.providerCollateralLocked;
        agreement.buyerEscrowLocked = 0;
        agreement.providerCollateralLocked = 0;
        agreement.state = SettlementState.SETTLED;

        // Neutral unwind: escrow back to buyer, collateral back to provider.
        claimable[agreement.buyer] += buyerAmount;
        claimable[agreement.provider] += providerAmount;

        emit TimeoutResolutionApplied(agreementId, buyerAmount, providerAmount);
    }

    function withdraw() external nonReentrant {
        uint256 amount = claimable[msg.sender];
        if (amount == 0) revert NothingToWithdraw();

        claimable[msg.sender] = 0;
        (bool ok, ) = payable(msg.sender).call{value: amount}("");
        if (!ok) revert NativeTransferFailed();
        emit Withdrawal(msg.sender, amount);
    }

    function _settleAccept(bytes32 agreementId, Agreement storage agreement) private {
        uint256 providerCredit = uint256(agreement.buyerEscrowLocked) + uint256(agreement.providerCollateralLocked);
        agreement.buyerEscrowLocked = 0;
        agreement.providerCollateralLocked = 0;
        agreement.state = SettlementState.SETTLED;
        claimable[agreement.provider] += providerCredit;
        emit AgreementSettled(agreementId, Decision.ACCEPT, 0, providerCredit);
    }

    function _settleReject(bytes32 agreementId, Agreement storage agreement) private {
        uint256 collateral = agreement.providerCollateralLocked;
        uint256 penalty = (collateral * agreement.rejectPenaltyBps) / 10_000;
        uint256 buyerCredit = uint256(agreement.buyerEscrowLocked) + penalty;
        uint256 providerCredit = collateral - penalty;

        agreement.buyerEscrowLocked = 0;
        agreement.providerCollateralLocked = 0;
        agreement.state = SettlementState.SETTLED;

        claimable[agreement.buyer] += buyerCredit;
        claimable[agreement.provider] += providerCredit;
        emit AgreementSettled(agreementId, Decision.REJECT, buyerCredit, providerCredit);
    }

    function _agreement(bytes32 agreementId) private view returns (Agreement storage agreement) {
        agreement = agreements[agreementId];
        if (agreement.state == SettlementState.NONE) revert AgreementNotFound();
    }

    function _requireState(Agreement storage agreement, SettlementState expected) private view {
        if (agreement.state != expected) revert InvalidState(expected, agreement.state);
    }

    receive() external payable {
        revert IncorrectValue(0, msg.value);
    }
}
