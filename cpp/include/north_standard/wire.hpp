#pragma once

#include "north_standard/json.hpp"
#include "north_standard/types.hpp"

#include <string>

namespace north_standard {

[[nodiscard]] JsonValue to_json(const ComputeContract& value);
[[nodiscard]] JsonValue to_json(const EvidenceRecord& value);
[[nodiscard]] JsonValue to_json(const EvidenceBundle& value);

[[nodiscard]] ComputeContract compute_contract_from_json(const JsonValue& value);
[[nodiscard]] EvidenceRecord evidence_record_from_json(const JsonValue& value);
[[nodiscard]] EvidenceBundle evidence_bundle_from_json(const JsonValue& value);

[[nodiscard]] JsonValue settlement_payload(
    const VerifierResult& value,
    const std::string& evidence_root
);

[[nodiscard]] std::string contract_hash(const ComputeContract& value);
[[nodiscard]] std::string evidence_bundle_root(const EvidenceBundle& value);
[[nodiscard]] std::string settlement_hash(
    const VerifierResult& value,
    const std::string& evidence_root
);

} // namespace north_standard
