#include "north_standard/scenarios.hpp"

#include <algorithm>
#include <stdexcept>
#include <utility>

namespace north_standard {
namespace {

[[nodiscard]] EvidenceRecord record(
    const ComputeContract& contract,
    std::string evidence_id,
    EvidenceType evidence_type,
    std::int64_t sequence_number,
    EvidencePayload payload,
    std::optional<std::string> session_id = std::nullopt,
    std::string producer_id = "verifier-fixture",
    std::optional<std::string> nonce = std::nullopt
) {
    const std::int64_t observed = contract.delivery_start +
        std::min(sequence_number * 10, contract.duration_seconds - 1);

    EvidenceRecord out;
    out.evidence_id = std::move(evidence_id);
    out.evidence_type = evidence_type;
    out.producer_id = std::move(producer_id);
    out.contract_id = contract.contract_id;
    out.session_id = session_id.value_or(contract.session_id);
    out.observed_at = observed;
    out.received_at = observed + 1;
    out.sequence_number = sequence_number;
    out.payload = std::move(payload);
    out.nonce = nonce.has_value() ? std::move(nonce) : std::optional<std::string>{"nonce-" + out.evidence_id};
    out.authentication_valid = true;
    out.trust_tier = evidence_type == EvidenceType::ExternalProbe ? "T4" : "T1";
    return out;
}

[[nodiscard]] std::vector<EvidenceRecord> healthy_records(const ComputeContract& contract) {
    EvidencePayload binding_payload;
    binding_payload.bound = true;

    EvidencePayload runtime_payload;
    runtime_payload.usable = true;
    runtime_payload.runtime_profile_id = contract.runtime_profile_id;

    EvidencePayload telemetry_payload;
    telemetry_payload.service_state = "HEALTHY";

    EvidencePayload challenge_1;
    challenge_1.score = 0.96;
    challenge_1.timed_out = false;

    EvidencePayload challenge_2;
    challenge_2.score = 1.01;
    challenge_2.timed_out = false;

    EvidencePayload challenge_3;
    challenge_3.score = 0.93;
    challenge_3.timed_out = false;

    EvidencePayload probe_payload;
    probe_payload.result = "SUCCESS";
    probe_payload.attribution = "NONE";

    std::vector<EvidenceRecord> records;
    records.push_back(record(
        contract, "bind-1", EvidenceType::SessionBinding, 1, std::move(binding_payload),
        std::nullopt, "provider-session-key"
    ));
    records.push_back(record(
        contract, "runtime-1", EvidenceType::RuntimeCheck, 2, std::move(runtime_payload)
    ));
    records.push_back(record(
        contract, "telemetry-1", EvidenceType::Telemetry, 3, std::move(telemetry_payload),
        std::nullopt, "provider-agent"
    ));
    records.push_back(record(
        contract, "challenge-1", EvidenceType::Challenge, 4, std::move(challenge_1)
    ));
    records.push_back(record(
        contract, "challenge-2", EvidenceType::Challenge, 5, std::move(challenge_2)
    ));
    records.push_back(record(
        contract, "challenge-3", EvidenceType::Challenge, 6, std::move(challenge_3)
    ));
    records.push_back(record(
        contract, "probe-1", EvidenceType::ExternalProbe, 7, std::move(probe_payload),
        std::nullopt, "independent-probe-a"
    ));
    return records;
}

} // namespace

ComputeContract demo_contract(std::string contract_id, std::string session_id) {
    ComputeContract contract;
    contract.contract_id = std::move(contract_id);
    contract.contract_class_id = "TEST-NVIDIA-GPU-PROFILE-v0.1";
    contract.provider_id = "provider-demo";
    contract.buyer_id = "buyer-demo";
    contract.session_id = std::move(session_id);
    contract.runtime_profile_id = "CUDA-TEST-RUNTIME-v0.1";
    contract.delivery_start = 1'800'000'000;
    contract.duration_seconds = 600;
    contract.sla_policy_id = "SLA-v0.1";
    contract.benchmark_profile_id = "GPU-SERVICE-CHALLENGE-v0.1";
    contract.performance_min_score = 0.80;
    contract.verifier_policy_id = "VERIFIER-v0.1";
    contract.settlement_policy_id = "SETTLEMENT-v0.1";
    contract.research_mode = true;
    return contract;
}

std::pair<ComputeContract, EvidenceBundle> simulate_scenario(Scenario scenario) {
    ComputeContract contract = demo_contract();
    auto records = healthy_records(contract);

    if (scenario == Scenario::ReplayedEvidence) {
        EvidencePayload payload;
        payload.bound = true;
        records.front() = record(
            contract,
            "bind-replayed",
            EvidenceType::SessionBinding,
            1,
            std::move(payload),
            "session-from-another-contract",
            "provider-session-key"
        );
    } else if (scenario == Scenario::ConstantThrottle) {
        records.erase(
            std::remove_if(
                records.begin(), records.end(),
                [](const EvidenceRecord& item) {
                    return item.evidence_type == EvidenceType::Challenge;
                }
            ),
            records.end()
        );
        const double scores[] = {0.56, 0.58, 0.55};
        for (std::size_t offset = 0; offset < 3; ++offset) {
            const std::int64_t sequence = static_cast<std::int64_t>(offset) + 4;
            EvidencePayload payload;
            payload.score = scores[offset];
            payload.timed_out = false;
            records.push_back(record(
                contract,
                "challenge-throttle-" + std::to_string(sequence),
                EvidenceType::Challenge,
                sequence,
                std::move(payload)
            ));
        }
    } else if (scenario == Scenario::AmbiguousNetworkFailure) {
        records.erase(
            std::remove_if(
                records.begin(), records.end(),
                [](const EvidenceRecord& item) {
                    return item.evidence_type == EvidenceType::ExternalProbe;
                }
            ),
            records.end()
        );
        EvidencePayload payload;
        payload.result = "FAILURE";
        payload.attribution = "UNKNOWN";
        records.push_back(record(
            contract,
            "probe-ambiguous",
            EvidenceType::ExternalProbe,
            7,
            std::move(payload),
            std::nullopt,
            "buyer-edge-probe"
        ));
    }

    std::sort(
        records.begin(), records.end(),
        [](const EvidenceRecord& lhs, const EvidenceRecord& rhs) {
            if (lhs.observed_at != rhs.observed_at) {
                return lhs.observed_at < rhs.observed_at;
            }
            return lhs.evidence_id < rhs.evidence_id;
        }
    );

    EvidenceBundle bundle;
    bundle.contract_id = contract.contract_id;
    bundle.session_id = contract.session_id;
    bundle.records = std::move(records);
    return {std::move(contract), std::move(bundle)};
}

Scenario scenario_from_string(std::string_view value) {
    if (value == "healthy_service") return Scenario::HealthyService;
    if (value == "replayed_evidence") return Scenario::ReplayedEvidence;
    if (value == "constant_throttle") return Scenario::ConstantThrottle;
    if (value == "ambiguous_network_failure") return Scenario::AmbiguousNetworkFailure;
    throw std::invalid_argument("unknown scenario");
}

const char* to_string(Scenario scenario) noexcept {
    switch (scenario) {
        case Scenario::HealthyService: return "healthy_service";
        case Scenario::ReplayedEvidence: return "replayed_evidence";
        case Scenario::ConstantThrottle: return "constant_throttle";
        case Scenario::AmbiguousNetworkFailure: return "ambiguous_network_failure";
    }
    return "unknown";
}

} // namespace north_standard
