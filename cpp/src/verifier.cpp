#include "north_standard/verifier.hpp"

#include <algorithm>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>

namespace north_standard {
namespace {

using RecordRefs = std::vector<const EvidenceRecord*>;

[[nodiscard]] std::vector<std::string> refs(const RecordRefs& records) {
    std::vector<std::string> out;
    out.reserve(records.size());
    for (const auto* record : records) {
        out.push_back(record->evidence_id);
    }
    return out;
}

[[nodiscard]] RecordRefs records_of(const EvidenceBundle& bundle, EvidenceType type) {
    RecordRefs out;
    for (const auto& record : bundle.records) {
        if (record.evidence_type == type) {
            out.push_back(&record);
        }
    }
    return out;
}

[[nodiscard]] ClaimResult binding_claim(
    const ComputeContract& contract,
    const EvidenceBundle& bundle,
    const VerifierPolicy& policy
) {
    const auto records = records_of(bundle, EvidenceType::SessionBinding);
    if (records.empty()) {
        return {"session.binding", ClaimState::Unknown, {"SESSION_BINDING_MISSING"}};
    }

    RecordRefs wrong_contract;
    for (const auto* record : records) {
        if (record->contract_id != contract.contract_id) {
            wrong_contract.push_back(record);
        }
    }
    if (!wrong_contract.empty() || bundle.contract_id != contract.contract_id) {
        return {
            "session.binding",
            ClaimState::Contradicting,
            {"SESSION_CONTRACT_MISMATCH"},
            refs(wrong_contract.empty() ? records : wrong_contract),
        };
    }

    RecordRefs wrong_session;
    for (const auto* record : records) {
        if (record->session_id != contract.session_id) {
            wrong_session.push_back(record);
        }
    }
    if (!wrong_session.empty() || bundle.session_id != contract.session_id) {
        return {
            "session.binding",
            ClaimState::Contradicting,
            {"SESSION_ID_MISMATCH"},
            refs(wrong_session.empty() ? records : wrong_session),
        };
    }

    RecordRefs invalid_auth;
    for (const auto* record : records) {
        if (!record->authentication_valid) {
            invalid_auth.push_back(record);
        }
    }
    if (!invalid_auth.empty()) {
        return {
            "session.binding",
            policy.reject_invalid_authentication ? ClaimState::Invalid : ClaimState::Unknown,
            {"SESSION_SIGNATURE_INVALID"},
            refs(invalid_auth),
        };
    }

    if (policy.require_unique_nonces) {
        std::unordered_map<std::string, std::size_t> counts;
        for (const auto* record : records) {
            if (record->nonce.has_value()) {
                ++counts[*record->nonce];
            }
        }
        std::size_t duplicate_count = 0;
        for (const auto& [nonce, count] : counts) {
            (void)nonce;
            if (count > 1) {
                ++duplicate_count;
            }
        }
        if (duplicate_count > 0) {
            ClaimResult result{
                "session.binding",
                ClaimState::Contradicting,
                {"EVIDENCE_NONCE_REPLAY"},
                refs(records),
            };
            result.numeric_metrics["duplicate_nonce_count"] = static_cast<double>(duplicate_count);
            return result;
        }
    }

    return {"session.binding", ClaimState::Affirming, {}, refs(records)};
}

[[nodiscard]] ClaimResult runtime_claim(
    const ComputeContract& contract,
    const EvidenceBundle& bundle
) {
    const auto records = records_of(bundle, EvidenceType::RuntimeCheck);
    RecordRefs valid;
    for (const auto* record : records) {
        if (record->contract_id == contract.contract_id &&
            record->session_id == contract.session_id &&
            record->authentication_valid) {
            valid.push_back(record);
        }
    }
    if (valid.empty()) {
        return {"service.runtime", ClaimState::Unknown, {"RUNTIME_EVIDENCE_MISSING"}};
    }

    RecordRefs incompatible;
    for (const auto* record : valid) {
        const bool usable = record->payload.usable.value_or(false);
        const bool profile_matches = record->payload.runtime_profile_id.has_value() &&
            *record->payload.runtime_profile_id == contract.runtime_profile_id;
        if (!usable || !profile_matches) {
            incompatible.push_back(record);
        }
    }
    if (!incompatible.empty()) {
        return {
            "service.runtime",
            ClaimState::Contradicting,
            {"RUNTIME_PROFILE_BREACH"},
            refs(incompatible),
        };
    }

    return {"service.runtime", ClaimState::Affirming, {}, refs(valid)};
}

[[nodiscard]] ClaimResult performance_claim(
    const ComputeContract& contract,
    const EvidenceBundle& bundle,
    const VerifierPolicy& policy
) {
    const auto records = records_of(bundle, EvidenceType::Challenge);
    RecordRefs valid;
    for (const auto* record : records) {
        if (record->contract_id == contract.contract_id &&
            record->session_id == contract.session_id &&
            record->authentication_valid &&
            !record->payload.timed_out.value_or(false) &&
            record->payload.score.has_value()) {
            valid.push_back(record);
        }
    }

    if (valid.size() < policy.minimum_valid_challenges) {
        ClaimResult result{
            "service.performance",
            ClaimState::Unknown,
            {"CHALLENGE_INSUFFICIENT_COUNT"},
            refs(valid),
        };
        result.numeric_metrics["valid_challenges"] = static_cast<double>(valid.size());
        result.numeric_metrics["required"] = static_cast<double>(policy.minimum_valid_challenges);
        return result;
    }

    RecordRefs breach_records;
    double minimum_score = *valid.front()->payload.score;
    double maximum_score = minimum_score;
    double score_sum = 0.0;
    for (const auto* record : valid) {
        const double score = *record->payload.score;
        minimum_score = std::min(minimum_score, score);
        maximum_score = std::max(maximum_score, score);
        score_sum += score;
        if (score < contract.performance_min_score) {
            breach_records.push_back(record);
        }
    }

    ClaimResult result;
    result.claim_id = "service.performance";
    result.numeric_metrics["valid_challenges"] = static_cast<double>(valid.size());
    result.numeric_metrics["breach_challenges"] = static_cast<double>(breach_records.size());
    result.numeric_metrics["minimum_score"] = minimum_score;
    result.numeric_metrics["maximum_score"] = maximum_score;
    result.numeric_metrics["mean_score"] = score_sum / static_cast<double>(valid.size());
    result.numeric_metrics["contract_floor"] = contract.performance_min_score;
    result.string_metrics["threshold_status"] = contract.research_mode
        ? "EXPERIMENT_DEFINED"
        : "CONTRACT_DEFINED";

    if (breach_records.size() >= policy.minimum_breach_challenges) {
        result.state = ClaimState::Contradicting;
        result.reason_codes = {"CHALLENGE_PERFORMANCE_BREACH"};
        result.evidence_refs = refs(breach_records);
        return result;
    }

    if (!breach_records.empty()) {
        result.state = ClaimState::Unknown;
        result.reason_codes = {"CHALLENGE_MIXED_PERFORMANCE"};
        result.evidence_refs = refs(valid);
        return result;
    }

    result.state = ClaimState::Affirming;
    result.evidence_refs = refs(valid);
    return result;
}

[[nodiscard]] ClaimResult availability_claim(
    const ComputeContract& contract,
    const EvidenceBundle& bundle
) {
    RecordRefs telemetry;
    for (const auto* record : records_of(bundle, EvidenceType::Telemetry)) {
        if (record->contract_id == contract.contract_id &&
            record->session_id == contract.session_id &&
            record->authentication_valid) {
            telemetry.push_back(record);
        }
    }

    RecordRefs probes;
    for (const auto* record : records_of(bundle, EvidenceType::ExternalProbe)) {
        if (record->contract_id == contract.contract_id &&
            record->session_id == contract.session_id &&
            record->authentication_valid) {
            probes.push_back(record);
        }
    }

    RecordRefs challenges;
    for (const auto* record : records_of(bundle, EvidenceType::Challenge)) {
        if (record->contract_id == contract.contract_id &&
            record->session_id == contract.session_id &&
            record->authentication_valid) {
            challenges.push_back(record);
        }
    }

    RecordRefs provider_fail_probes;
    for (const auto* record : probes) {
        if (record->payload.result == std::optional<std::string>{"FAILURE"} &&
            record->payload.attribution == std::optional<std::string>{"PROVIDER"}) {
            provider_fail_probes.push_back(record);
        }
    }

    RecordRefs provider_fail_telemetry;
    for (const auto* record : telemetry) {
        if (record->payload.service_state == std::optional<std::string>{"UNAVAILABLE"}) {
            provider_fail_telemetry.push_back(record);
        }
    }

    RecordRefs timed_out_challenges;
    for (const auto* record : challenges) {
        if (record->payload.timed_out.value_or(false) &&
            record->payload.timeout_attribution == std::optional<std::string>{"PROVIDER"}) {
            timed_out_challenges.push_back(record);
        }
    }

    if (!provider_fail_probes.empty() &&
        (!provider_fail_telemetry.empty() || !timed_out_challenges.empty())) {
        RecordRefs all = provider_fail_probes;
        all.insert(all.end(), provider_fail_telemetry.begin(), provider_fail_telemetry.end());
        all.insert(all.end(), timed_out_challenges.begin(), timed_out_challenges.end());
        return {
            "service.availability",
            ClaimState::Contradicting,
            {"AVAILABILITY_PROVIDER_FAILURE"},
            refs(all),
        };
    }

    RecordRefs ambiguous_failures;
    for (const auto* record : probes) {
        if (record->payload.result != std::optional<std::string>{"FAILURE"}) {
            continue;
        }
        const auto& attribution = record->payload.attribution;
        if (!attribution.has_value() || *attribution == "UNKNOWN" || *attribution == "NETWORK") {
            ambiguous_failures.push_back(record);
        }
    }
    if (!ambiguous_failures.empty()) {
        RecordRefs all = ambiguous_failures;
        all.insert(all.end(), telemetry.begin(), telemetry.end());
        all.insert(all.end(), challenges.begin(), challenges.end());
        return {
            "service.availability",
            ClaimState::Unknown,
            {"AVAILABILITY_EVIDENCE_CONFLICT"},
            refs(all),
        };
    }

    RecordRefs healthy_telemetry;
    for (const auto* record : telemetry) {
        if (record->payload.service_state == std::optional<std::string>{"HEALTHY"}) {
            healthy_telemetry.push_back(record);
        }
    }

    RecordRefs successful_probes;
    for (const auto* record : probes) {
        if (record->payload.result == std::optional<std::string>{"SUCCESS"}) {
            successful_probes.push_back(record);
        }
    }

    RecordRefs successful_challenges;
    for (const auto* record : challenges) {
        if (!record->payload.timed_out.value_or(false)) {
            successful_challenges.push_back(record);
        }
    }

    if (!healthy_telemetry.empty() &&
        (!successful_probes.empty() || !successful_challenges.empty())) {
        RecordRefs all = healthy_telemetry;
        all.insert(all.end(), successful_probes.begin(), successful_probes.end());
        all.insert(all.end(), successful_challenges.begin(), successful_challenges.end());
        return {"service.availability", ClaimState::Affirming, {}, refs(all)};
    }

    RecordRefs all = telemetry;
    all.insert(all.end(), probes.begin(), probes.end());
    all.insert(all.end(), challenges.begin(), challenges.end());
    return {
        "service.availability",
        ClaimState::Unknown,
        {"AVAILABILITY_EVIDENCE_INSUFFICIENT"},
        refs(all),
    };
}

[[nodiscard]] std::vector<std::string> bundle_integrity_errors(
    const ComputeContract& contract,
    const EvidenceBundle& bundle
) {
    std::unordered_set<std::string> seen_ids;
    std::unordered_map<std::string, std::unordered_set<std::int64_t>> seen_sequences;
    std::unordered_set<std::string> errors;

    for (const auto& record : bundle.records) {
        if (!seen_ids.insert(record.evidence_id).second) {
            errors.insert("DUPLICATE_EVIDENCE_ID");
        }

        const std::string key = record.producer_id + ":" + record.session_id;
        if (!seen_sequences[key].insert(record.sequence_number).second) {
            errors.insert("DUPLICATE_SEQUENCE_NUMBER");
        }

        if (record.observed_at < contract.delivery_start - 60) {
            errors.insert("EVIDENCE_BEFORE_DELIVERY_WINDOW");
        }
        if (record.observed_at > contract.delivery_end() + 60) {
            errors.insert("EVIDENCE_AFTER_DELIVERY_WINDOW");
        }
    }

    std::vector<std::string> out(errors.begin(), errors.end());
    std::sort(out.begin(), out.end());
    return out;
}

[[nodiscard]] bool contains(const std::vector<std::string>& values, const std::string& needle) {
    return std::find(values.begin(), values.end(), needle) != values.end();
}

[[nodiscard]] std::vector<std::string> sorted_unique(std::vector<std::string> values) {
    std::sort(values.begin(), values.end());
    values.erase(std::unique(values.begin(), values.end()), values.end());
    return values;
}

} // namespace

const char* to_string(Decision value) noexcept {
    switch (value) {
        case Decision::Accept: return "ACCEPT";
        case Decision::Reject: return "REJECT";
        case Decision::Inconclusive: return "INCONCLUSIVE";
    }
    return "INCONCLUSIVE";
}

const char* to_string(ClaimState value) noexcept {
    switch (value) {
        case ClaimState::Affirming: return "AFFIRMING";
        case ClaimState::Contradicting: return "CONTRADICTING";
        case ClaimState::Unknown: return "UNKNOWN";
        case ClaimState::NotEvaluated: return "NOT_EVALUATED";
        case ClaimState::Invalid: return "INVALID";
    }
    return "UNKNOWN";
}

VerifierResult verify(
    const ComputeContract& contract,
    const EvidenceBundle& bundle,
    const VerifierPolicy& policy
) {
    if (policy.policy_id != contract.verifier_policy_id) {
        throw std::invalid_argument("verifier policy mismatch");
    }

    const auto integrity_errors = bundle_integrity_errors(contract, bundle);

    VerifierResult result;
    result.contract_id = contract.contract_id;
    result.session_id = contract.session_id;
    result.verifier_policy_id = policy.policy_id;
    result.research_mode = contract.research_mode;
    result.claims.emplace("session.binding", binding_claim(contract, bundle, policy));
    result.claims.emplace("service.runtime", runtime_claim(contract, bundle));
    result.claims.emplace("service.availability", availability_claim(contract, bundle));
    result.claims.emplace("service.performance", performance_claim(contract, bundle, policy));

    const bool fatal_integrity = contains(integrity_errors, "DUPLICATE_EVIDENCE_ID") ||
        contains(integrity_errors, "DUPLICATE_SEQUENCE_NUMBER");

    std::vector<const ClaimResult*> mandatory;
    for (const auto& claim_id : contract.mandatory_claims) {
        const auto it = result.claims.find(claim_id);
        if (it != result.claims.end()) {
            mandatory.push_back(&it->second);
        }
    }

    if (fatal_integrity) {
        result.decision = Decision::Reject;
        for (const auto& error : integrity_errors) {
            if (error == "DUPLICATE_EVIDENCE_ID" || error == "DUPLICATE_SEQUENCE_NUMBER") {
                result.reason_codes.push_back(error);
            }
        }
        result.reason_codes = sorted_unique(std::move(result.reason_codes));
    } else {
        const auto collect_for_state = [&mandatory](ClaimState state) {
            std::vector<std::string> codes;
            for (const auto* claim : mandatory) {
                if (claim->state == state) {
                    codes.insert(codes.end(), claim->reason_codes.begin(), claim->reason_codes.end());
                }
            }
            return sorted_unique(std::move(codes));
        };

        const bool has_contradiction = std::any_of(
            mandatory.begin(), mandatory.end(),
            [](const ClaimResult* claim) { return claim->state == ClaimState::Contradicting; }
        );
        const bool has_invalid = std::any_of(
            mandatory.begin(), mandatory.end(),
            [](const ClaimResult* claim) { return claim->state == ClaimState::Invalid; }
        );
        const bool has_unknown = std::any_of(
            mandatory.begin(), mandatory.end(),
            [](const ClaimResult* claim) { return claim->state == ClaimState::Unknown; }
        );
        const bool all_affirming = std::all_of(
            mandatory.begin(), mandatory.end(),
            [](const ClaimResult* claim) { return claim->state == ClaimState::Affirming; }
        );

        if (has_contradiction) {
            result.decision = Decision::Reject;
            result.reason_codes = collect_for_state(ClaimState::Contradicting);
        } else if (has_invalid) {
            result.decision = Decision::Reject;
            result.reason_codes = collect_for_state(ClaimState::Invalid);
        } else if (has_unknown) {
            result.decision = Decision::Inconclusive;
            result.reason_codes = collect_for_state(ClaimState::Unknown);
        } else if (all_affirming) {
            result.decision = Decision::Accept;
        } else {
            result.decision = Decision::Inconclusive;
            result.reason_codes = {"UNRESOLVED_MANDATORY_CLAIM_STATE"};
        }
    }

    if (!fatal_integrity && !integrity_errors.empty()) {
        result.reason_codes.insert(
            result.reason_codes.end(), integrity_errors.begin(), integrity_errors.end()
        );
        result.reason_codes = sorted_unique(std::move(result.reason_codes));
    }

    return result;
}

} // namespace north_standard
