#include "north_standard/json.hpp"
#include "north_standard/scenarios.hpp"
#include "north_standard/verifier.hpp"
#include "north_standard/wire.hpp"

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <unordered_map>

namespace {

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

void test_sha256_vectors() {
    require(
        north_standard::sha256_hex("") ==
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "SHA-256 empty vector mismatch"
    );
    require(
        north_standard::sha256_hex("abc") ==
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        "SHA-256 abc vector mismatch"
    );
}

void test_canonical_json() {
    const auto parsed = north_standard::parse_json(
        "{\"z\":1,\"a\":1.0,\"s\":\"x\\nΩ\",\"arr\":[true,null,-0.0]}"
    );
    require(
        north_standard::canonical_json(parsed) ==
            "{\"a\":1.0,\"arr\":[true,null,-0.0],\"s\":\"x\\nΩ\",\"z\":1}",
        "canonical JSON mismatch"
    );
}

void test_scenario_commitments() {
    const std::unordered_map<std::string, std::string> bundle_roots{
        {"healthy_service", "2a5a3fb56a9ee3cef4f27a5b59f1dbe05e89b3ebc2409421d8c98c093a53f4d2"},
        {"replayed_evidence", "42fe1b9909ab1f06e1915ba257aa3c411c2437f4a32ecb37aad22cfb3652fa81"},
        {"constant_throttle", "697a5259ce9558ace655d38c11a821bc6e91b0422f4b5180e4e386844a5b49bf"},
        {"ambiguous_network_failure", "d70707d881195266bafcfa7e04b0c1e508a24475885666de87ae0168ffc3d092"},
    };

    for (const auto scenario : {
        north_standard::Scenario::HealthyService,
        north_standard::Scenario::ReplayedEvidence,
        north_standard::Scenario::ConstantThrottle,
        north_standard::Scenario::AmbiguousNetworkFailure,
    }) {
        const auto [contract, bundle] = north_standard::simulate_scenario(scenario);
        const auto expected_contract =
            "6ce6940b7dfad6dff916105b64a946142666b02221fdb953dc5e781c0d25f63c";
        require(north_standard::contract_hash(contract) == expected_contract, "contract hash mismatch");
        require(
            north_standard::evidence_bundle_root(bundle) == bundle_roots.at(north_standard::to_string(scenario)),
            std::string{"bundle root mismatch for "} + north_standard::to_string(scenario)
        );
    }
}

} // namespace

int main() {
    try {
        test_sha256_vectors();
        test_canonical_json();
        test_scenario_commitments();
        std::cout << "north-standard-json-tests: 3 groups passed\n";
        return EXIT_SUCCESS;
    } catch (const std::exception& error) {
        std::cerr << "north-standard-json-tests: FAILED: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
