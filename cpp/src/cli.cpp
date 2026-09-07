#include "north_standard/json.hpp"
#include "north_standard/scenarios.hpp"
#include "north_standard/verifier.hpp"
#include "north_standard/wire.hpp"

#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>

namespace {

std::string read_stdin() {
    return std::string(
        std::istreambuf_iterator<char>{std::cin},
        std::istreambuf_iterator<char>{}
    );
}

void print_reasons(const std::vector<std::string>& reasons) {
    for (std::size_t index = 0; index < reasons.size(); ++index) {
        if (index > 0) std::cout << ',';
        std::cout << reasons[index];
    }
}

int run_simulate(const std::string& scenario_name) {
    const auto scenario = north_standard::scenario_from_string(scenario_name);
    const auto [contract, bundle] = north_standard::simulate_scenario(scenario);
    const auto result = north_standard::verify(contract, bundle);

    std::cout << north_standard::to_string(result.decision) << '|';
    print_reasons(result.reason_codes);
    std::cout << '\n';
    return 0;
}

int run_verify_json() {
    const auto root = north_standard::parse_json(read_stdin());
    const auto* object = std::get_if<north_standard::JsonValue::Object>(&root.value);
    if (object == nullptr) throw std::invalid_argument("wire input must be a JSON object");

    const auto contract_it = object->find("contract");
    const auto bundle_it = object->find("evidence_bundle");
    if (contract_it == object->end() || bundle_it == object->end()) {
        throw std::invalid_argument("wire input requires contract and evidence_bundle");
    }

    const auto contract = north_standard::compute_contract_from_json(contract_it->second);
    const auto bundle = north_standard::evidence_bundle_from_json(bundle_it->second);
    const auto result = north_standard::verify(contract, bundle);
    const auto bundle_root = north_standard::evidence_bundle_root(bundle);

    std::cout
        << north_standard::contract_hash(contract) << '|'
        << bundle_root << '|'
        << north_standard::settlement_hash(result, bundle_root) << '|'
        << north_standard::to_string(result.decision) << '|';
    print_reasons(result.reason_codes);
    std::cout << '\n';
    return 0;
}

} // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 3 && std::string{argv[1]} == "simulate") {
            return run_simulate(argv[2]);
        }

        if (argc == 2 && std::string{argv[1]} == "verify-json") {
            return run_verify_json();
        }

        if (argc == 2 && std::string{argv[1]} == "canonicalize-json") {
            std::cout << north_standard::canonical_json(north_standard::parse_json(read_stdin())) << '\n';
            return 0;
        }

        if (argc == 2 && std::string{argv[1]} == "hash-json") {
            const auto parsed = north_standard::parse_json(read_stdin());
            std::cout << north_standard::canonical_sha256(parsed) << '\n';
            return 0;
        }

        std::cerr
            << "usage:\n"
            << "  north-standard-cpp simulate <scenario>\n"
            << "  north-standard-cpp verify-json < wire.json\n"
            << "  north-standard-cpp canonicalize-json < value.json\n"
            << "  north-standard-cpp hash-json < value.json\n";
        return 2;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
