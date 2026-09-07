#include "north_standard/scenarios.hpp"
#include "north_standard/verifier.hpp"

#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc, char** argv) {
    if (argc != 3 || std::string{argv[1]} != "simulate") {
        std::cerr << "usage: north-standard-cpp simulate <scenario>\n";
        return 2;
    }

    try {
        const auto scenario = north_standard::scenario_from_string(argv[2]);
        const auto [contract, bundle] = north_standard::simulate_scenario(scenario);
        const auto result = north_standard::verify(contract, bundle);

        std::cout << north_standard::to_string(result.decision) << '|';
        for (std::size_t index = 0; index < result.reason_codes.size(); ++index) {
            if (index > 0) {
                std::cout << ',';
            }
            std::cout << result.reason_codes[index];
        }
        std::cout << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
