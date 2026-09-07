#include "north_standard/scenarios.hpp"
#include "north_standard/verifier.hpp"

#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

void require(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

bool has_reason(const north_standard::VerifierResult& result, const std::string& code) {
    return std::find(result.reason_codes.begin(), result.reason_codes.end(), code) !=
        result.reason_codes.end();
}

void test_scenario(
    north_standard::Scenario scenario,
    north_standard::Decision expected,
    const std::string& expected_reason = {}
) {
    const auto [contract, bundle] = north_standard::simulate_scenario(scenario);
    const auto result = north_standard::verify(contract, bundle);
    require(result.decision == expected, std::string{"unexpected decision for "} + north_standard::to_string(scenario));
    if (!expected_reason.empty()) {
        require(has_reason(result, expected_reason), "missing expected reason code: " + expected_reason);
    }
}

void test_duplicate_evidence_id_is_fatal() {
    auto [contract, bundle] = north_standard::simulate_scenario(north_standard::Scenario::HealthyService);
    bundle.records.push_back(bundle.records.front());
    bundle.records.back().sequence_number = 999;
    const auto result = north_standard::verify(contract, bundle);
    require(result.decision == north_standard::Decision::Reject, "duplicate evidence id must reject");
    require(has_reason(result, "DUPLICATE_EVIDENCE_ID"), "duplicate evidence id reason missing");
}

void test_duplicate_sequence_is_fatal() {
    auto [contract, bundle] = north_standard::simulate_scenario(north_standard::Scenario::HealthyService);
    auto duplicate = bundle.records.front();
    duplicate.evidence_id = "bind-duplicate-sequence";
    bundle.records.push_back(std::move(duplicate));
    const auto result = north_standard::verify(contract, bundle);
    require(result.decision == north_standard::Decision::Reject, "duplicate sequence must reject");
    require(has_reason(result, "DUPLICATE_SEQUENCE_NUMBER"), "duplicate sequence reason missing");
}

void test_policy_mismatch_throws() {
    const auto [contract, bundle] = north_standard::simulate_scenario(north_standard::Scenario::HealthyService);
    north_standard::VerifierPolicy policy;
    policy.policy_id = "VERIFIER-v9";
    bool threw = false;
    try {
        (void)north_standard::verify(contract, bundle, policy);
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    require(threw, "policy mismatch must throw");
}

} // namespace

int main() {
    try {
        test_scenario(north_standard::Scenario::HealthyService, north_standard::Decision::Accept);
        test_scenario(
            north_standard::Scenario::ReplayedEvidence,
            north_standard::Decision::Reject,
            "SESSION_ID_MISMATCH"
        );
        test_scenario(
            north_standard::Scenario::ConstantThrottle,
            north_standard::Decision::Reject,
            "CHALLENGE_PERFORMANCE_BREACH"
        );
        test_scenario(
            north_standard::Scenario::AmbiguousNetworkFailure,
            north_standard::Decision::Inconclusive,
            "AVAILABILITY_EVIDENCE_CONFLICT"
        );
        test_duplicate_evidence_id_is_fatal();
        test_duplicate_sequence_is_fatal();
        test_policy_mismatch_throws();
        std::cout << "north-standard-cpp-tests: 7 passed\n";
        return EXIT_SUCCESS;
    } catch (const std::exception& error) {
        std::cerr << "north-standard-cpp-tests: FAILED: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
