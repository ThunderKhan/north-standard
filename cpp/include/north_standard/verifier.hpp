#pragma once

#include "north_standard/types.hpp"

namespace north_standard {

[[nodiscard]] VerifierResult verify(
    const ComputeContract& contract,
    const EvidenceBundle& bundle,
    const VerifierPolicy& policy = {}
);

} // namespace north_standard
