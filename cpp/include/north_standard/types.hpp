#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <utility>
#include <unordered_map>
#include <vector>

namespace north_standard {

enum class Decision {
    Accept,
    Reject,
    Inconclusive,
};

enum class ClaimState {
    Affirming,
    Contradicting,
    Unknown,
    NotEvaluated,
    Invalid,
};

enum class EvidenceType {
    SessionBinding,
    RuntimeCheck,
    Telemetry,
    Challenge,
    ExternalProbe,
    HardwareAttestation,
    AdminEvent,
};

struct ComputeContract {
    std::string schema_version{"compute-contract/0.1"};
    std::string contract_id;
    std::string contract_class_id;
    std::string provider_id;
    std::string buyer_id;
    std::string session_id;
    std::string runtime_profile_id;
    std::int64_t delivery_start{};
    std::int64_t duration_seconds{};
    std::string sla_policy_id;
    std::string benchmark_profile_id;
    double performance_min_score{};
    std::string verifier_policy_id{"VERIFIER-v0.1"};
    std::string settlement_policy_id{"SETTLEMENT-v0.1"};
    std::string evidence_schema_version{"evidence/0.1"};
    std::vector<std::string> mandatory_claims{
        "session.binding",
        "service.runtime",
        "service.availability",
        "service.performance",
    };
    bool research_mode{true};

    [[nodiscard]] std::int64_t delivery_end() const noexcept {
        return delivery_start + duration_seconds;
    }
};

struct EvidencePayload {
    std::optional<bool> bound;
    std::optional<bool> usable;
    std::optional<std::string> runtime_profile_id;
    std::optional<std::string> service_state;
    std::optional<double> score;
    std::optional<bool> timed_out;
    std::optional<std::string> timeout_attribution;
    std::optional<std::string> result;
    std::optional<std::string> attribution;
};

struct EvidenceRecord {
    std::string schema_version{"evidence/0.1"};
    std::string evidence_id;
    EvidenceType evidence_type{EvidenceType::AdminEvent};
    std::string producer_id;
    std::string contract_id;
    std::string session_id;
    std::int64_t observed_at{};
    std::int64_t received_at{};
    std::int64_t sequence_number{};
    EvidencePayload payload;
    std::optional<std::string> nonce;
    std::string replay_domain{"north-standard/v0.1"};
    bool authentication_valid{true};
    std::string trust_tier{"T1"};
};

struct EvidenceBundle {
    std::string schema_version{"evidence-bundle/0.1"};
    std::string contract_id;
    std::string session_id;
    std::vector<EvidenceRecord> records;
};

struct ClaimResult {
    std::string claim_id;
    ClaimState state{ClaimState::Unknown};
    std::vector<std::string> reason_codes;
    std::vector<std::string> evidence_refs;
    std::unordered_map<std::string, double> numeric_metrics;
    std::unordered_map<std::string, std::string> string_metrics;

    ClaimResult() = default;

    ClaimResult(
        std::string id,
        ClaimState claim_state,
        std::vector<std::string> reasons = {},
        std::vector<std::string> refs = {}
    )
        : claim_id(std::move(id)),
          state(claim_state),
          reason_codes(std::move(reasons)),
          evidence_refs(std::move(refs)) {}
};

struct VerifierPolicy {
    std::string policy_id{"VERIFIER-v0.1"};
    std::size_t minimum_valid_challenges{2};
    std::size_t minimum_breach_challenges{2};
    std::int64_t max_evidence_age_seconds{3600};
    bool reject_invalid_authentication{true};
    bool require_unique_nonces{true};
};

struct VerifierResult {
    std::string schema_version{"verifier-result/0.1"};
    std::string contract_id;
    std::string session_id;
    std::string verifier_policy_id;
    std::unordered_map<std::string, ClaimResult> claims;
    Decision decision{Decision::Inconclusive};
    std::vector<std::string> reason_codes;
    std::string verifier_build_id{"north-standard-cpp/v0.1"};
    bool research_mode{true};
};

[[nodiscard]] const char* to_string(Decision value) noexcept;
[[nodiscard]] const char* to_string(ClaimState value) noexcept;

} // namespace north_standard
