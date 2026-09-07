#pragma once

#include "north_standard/types.hpp"

#include <string_view>
#include <utility>

namespace north_standard {

enum class Scenario {
    HealthyService,
    ReplayedEvidence,
    ConstantThrottle,
    AmbiguousNetworkFailure,
};

[[nodiscard]] ComputeContract demo_contract(
    std::string contract_id = "contract-001",
    std::string session_id = "session-001"
);

[[nodiscard]] std::pair<ComputeContract, EvidenceBundle> simulate_scenario(Scenario scenario);
[[nodiscard]] Scenario scenario_from_string(std::string_view value);
[[nodiscard]] const char* to_string(Scenario scenario) noexcept;

} // namespace north_standard
