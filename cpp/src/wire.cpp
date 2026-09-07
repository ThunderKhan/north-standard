#include "north_standard/wire.hpp"

#include <cmath>
#include <stdexcept>
#include <string_view>
#include <type_traits>

namespace north_standard {
namespace {

JsonValue::Array strings(const std::vector<std::string>& values) {
    JsonValue::Array out;
    out.reserve(values.size());
    for (const auto& value : values) out.emplace_back(value);
    return out;
}

const char* evidence_type_name(EvidenceType type) {
    switch (type) {
        case EvidenceType::SessionBinding: return "SESSION_BINDING";
        case EvidenceType::RuntimeCheck: return "RUNTIME_CHECK";
        case EvidenceType::Telemetry: return "TELEMETRY";
        case EvidenceType::Challenge: return "CHALLENGE";
        case EvidenceType::ExternalProbe: return "EXTERNAL_PROBE";
        case EvidenceType::HardwareAttestation: return "HARDWARE_ATTESTATION";
        case EvidenceType::AdminEvent: return "ADMIN_EVENT";
    }
    throw std::logic_error("unknown evidence type");
}

EvidenceType evidence_type_from_name(const std::string& value) {
    if (value == "SESSION_BINDING") return EvidenceType::SessionBinding;
    if (value == "RUNTIME_CHECK") return EvidenceType::RuntimeCheck;
    if (value == "TELEMETRY") return EvidenceType::Telemetry;
    if (value == "CHALLENGE") return EvidenceType::Challenge;
    if (value == "EXTERNAL_PROBE") return EvidenceType::ExternalProbe;
    if (value == "HARDWARE_ATTESTATION") return EvidenceType::HardwareAttestation;
    if (value == "ADMIN_EVENT") return EvidenceType::AdminEvent;
    throw std::invalid_argument("unknown evidence_type: " + value);
}

const JsonValue::Object& as_object(const JsonValue& value, const char* context) {
    if (const auto* object = std::get_if<JsonValue::Object>(&value.value)) return *object;
    throw std::invalid_argument(std::string{context} + " must be an object");
}

const JsonValue::Array& as_array(const JsonValue& value, const char* context) {
    if (const auto* array = std::get_if<JsonValue::Array>(&value.value)) return *array;
    throw std::invalid_argument(std::string{context} + " must be an array");
}

const JsonValue& required(const JsonValue::Object& object, std::string_view key) {
    const std::string owned_key{key};
    const auto it = object.find(owned_key);
    if (it == object.end()) throw std::invalid_argument("missing required field: " + owned_key);
    return it->second;
}

std::string as_string(const JsonValue& value, const std::string& key) {
    if (const auto* text = std::get_if<std::string>(&value.value)) return *text;
    throw std::invalid_argument(key + " must be a string");
}

bool as_bool(const JsonValue& value, const std::string& key) {
    if (const auto* item = std::get_if<bool>(&value.value)) return *item;
    throw std::invalid_argument(key + " must be a boolean");
}

std::int64_t as_int(const JsonValue& value, const std::string& key) {
    if (const auto* item = std::get_if<std::int64_t>(&value.value)) return *item;
    throw std::invalid_argument(key + " must be an integer");
}

double as_number(const JsonValue& value, const std::string& key) {
    if (const auto* item = std::get_if<double>(&value.value)) return *item;
    if (const auto* item = std::get_if<std::int64_t>(&value.value)) return static_cast<double>(*item);
    throw std::invalid_argument(key + " must be a number");
}

std::vector<std::string> as_string_array(const JsonValue& value, const std::string& key) {
    std::vector<std::string> out;
    for (const auto& item : as_array(value, key.c_str())) out.push_back(as_string(item, key));
    return out;
}

JsonValue payload_json(const EvidencePayload& payload) {
    JsonValue::Object object = payload.extra;
    if (payload.bound.has_value()) object["bound"] = *payload.bound;
    if (payload.usable.has_value()) object["usable"] = *payload.usable;
    if (payload.runtime_profile_id.has_value()) object["runtime_profile_id"] = *payload.runtime_profile_id;
    if (payload.service_state.has_value()) object["service_state"] = *payload.service_state;
    if (payload.score.has_value()) object["score"] = *payload.score;
    if (payload.timed_out.has_value()) object["timed_out"] = *payload.timed_out;
    if (payload.timeout_attribution.has_value()) object["timeout_attribution"] = *payload.timeout_attribution;
    if (payload.result.has_value()) object["result"] = *payload.result;
    if (payload.attribution.has_value()) object["attribution"] = *payload.attribution;
    return object;
}

EvidencePayload payload_from_json(const JsonValue& value) {
    const auto& object = as_object(value, "payload");
    EvidencePayload payload;
    for (const auto& [key, item] : object) {
        if (key == "bound") payload.bound = as_bool(item, key);
        else if (key == "usable") payload.usable = as_bool(item, key);
        else if (key == "runtime_profile_id") payload.runtime_profile_id = as_string(item, key);
        else if (key == "service_state") payload.service_state = as_string(item, key);
        else if (key == "score") payload.score = as_number(item, key);
        else if (key == "timed_out") payload.timed_out = as_bool(item, key);
        else if (key == "timeout_attribution") payload.timeout_attribution = as_string(item, key);
        else if (key == "result") payload.result = as_string(item, key);
        else if (key == "attribution") payload.attribution = as_string(item, key);
        else payload.extra.emplace(key, item);
    }
    return payload;
}

} // namespace

JsonValue to_json(const ComputeContract& value) {
    return JsonValue::Object{
        {"benchmark_profile_id", value.benchmark_profile_id},
        {"buyer_id", value.buyer_id},
        {"contract_class_id", value.contract_class_id},
        {"contract_id", value.contract_id},
        {"delivery_start", value.delivery_start},
        {"duration_seconds", value.duration_seconds},
        {"evidence_schema_version", value.evidence_schema_version},
        {"mandatory_claims", strings(value.mandatory_claims)},
        {"performance_min_score", value.performance_min_score},
        {"provider_id", value.provider_id},
        {"research_mode", value.research_mode},
        {"runtime_profile_id", value.runtime_profile_id},
        {"schema_version", value.schema_version},
        {"settlement_policy_id", value.settlement_policy_id},
        {"sla_policy_id", value.sla_policy_id},
        {"session_id", value.session_id},
        {"verifier_policy_id", value.verifier_policy_id},
    };
}

JsonValue to_json(const EvidenceRecord& value) {
    return JsonValue::Object{
        {"authentication_valid", value.authentication_valid},
        {"contract_id", value.contract_id},
        {"evidence_id", value.evidence_id},
        {"evidence_type", evidence_type_name(value.evidence_type)},
        {"nonce", value.nonce.has_value() ? JsonValue{*value.nonce} : JsonValue{nullptr}},
        {"observed_at", value.observed_at},
        {"payload", payload_json(value.payload)},
        {"producer_id", value.producer_id},
        {"received_at", value.received_at},
        {"replay_domain", value.replay_domain},
        {"schema_version", value.schema_version},
        {"sequence_number", value.sequence_number},
        {"session_id", value.session_id},
        {"trust_tier", value.trust_tier},
    };
}

JsonValue to_json(const EvidenceBundle& value) {
    JsonValue::Array records;
    records.reserve(value.records.size());
    for (const auto& record : value.records) records.push_back(to_json(record));
    return JsonValue::Object{
        {"contract_id", value.contract_id},
        {"records", std::move(records)},
        {"schema_version", value.schema_version},
        {"session_id", value.session_id},
    };
}

ComputeContract compute_contract_from_json(const JsonValue& value) {
    const auto& object = as_object(value, "compute contract");
    ComputeContract contract;
    contract.schema_version = as_string(required(object, "schema_version"), "schema_version");
    contract.contract_id = as_string(required(object, "contract_id"), "contract_id");
    contract.contract_class_id = as_string(required(object, "contract_class_id"), "contract_class_id");
    contract.provider_id = as_string(required(object, "provider_id"), "provider_id");
    contract.buyer_id = as_string(required(object, "buyer_id"), "buyer_id");
    contract.session_id = as_string(required(object, "session_id"), "session_id");
    contract.runtime_profile_id = as_string(required(object, "runtime_profile_id"), "runtime_profile_id");
    contract.delivery_start = as_int(required(object, "delivery_start"), "delivery_start");
    contract.duration_seconds = as_int(required(object, "duration_seconds"), "duration_seconds");
    contract.sla_policy_id = as_string(required(object, "sla_policy_id"), "sla_policy_id");
    contract.benchmark_profile_id = as_string(required(object, "benchmark_profile_id"), "benchmark_profile_id");
    contract.performance_min_score = as_number(required(object, "performance_min_score"), "performance_min_score");
    contract.verifier_policy_id = as_string(required(object, "verifier_policy_id"), "verifier_policy_id");
    contract.settlement_policy_id = as_string(required(object, "settlement_policy_id"), "settlement_policy_id");
    contract.evidence_schema_version = as_string(required(object, "evidence_schema_version"), "evidence_schema_version");
    contract.mandatory_claims = as_string_array(required(object, "mandatory_claims"), "mandatory_claims");
    contract.research_mode = as_bool(required(object, "research_mode"), "research_mode");

    if (contract.schema_version != "compute-contract/0.1") throw std::invalid_argument("unsupported compute contract schema_version");
    if (contract.duration_seconds <= 0) throw std::invalid_argument("duration_seconds must be positive");
    if (contract.contract_id.empty() || contract.session_id.empty()) throw std::invalid_argument("contract_id and session_id are required");
    if (contract.performance_min_score < 0.0) throw std::invalid_argument("performance_min_score must be non-negative");
    return contract;
}

EvidenceRecord evidence_record_from_json(const JsonValue& value) {
    const auto& object = as_object(value, "evidence record");
    EvidenceRecord record;
    record.schema_version = as_string(required(object, "schema_version"), "schema_version");
    record.evidence_id = as_string(required(object, "evidence_id"), "evidence_id");
    record.evidence_type = evidence_type_from_name(as_string(required(object, "evidence_type"), "evidence_type"));
    record.producer_id = as_string(required(object, "producer_id"), "producer_id");
    record.contract_id = as_string(required(object, "contract_id"), "contract_id");
    record.session_id = as_string(required(object, "session_id"), "session_id");
    record.observed_at = as_int(required(object, "observed_at"), "observed_at");
    record.received_at = as_int(required(object, "received_at"), "received_at");
    record.sequence_number = as_int(required(object, "sequence_number"), "sequence_number");
    record.payload = payload_from_json(required(object, "payload"));
    const auto& nonce = required(object, "nonce");
    if (std::holds_alternative<std::nullptr_t>(nonce.value)) record.nonce.reset();
    else record.nonce = as_string(nonce, "nonce");
    record.replay_domain = as_string(required(object, "replay_domain"), "replay_domain");
    record.authentication_valid = as_bool(required(object, "authentication_valid"), "authentication_valid");
    record.trust_tier = as_string(required(object, "trust_tier"), "trust_tier");

    if (record.schema_version != "evidence/0.1") throw std::invalid_argument("unsupported evidence schema_version");
    if (record.sequence_number < 0) throw std::invalid_argument("sequence_number must be non-negative");
    if (record.received_at < record.observed_at) throw std::invalid_argument("received_at cannot precede observed_at");
    return record;
}

EvidenceBundle evidence_bundle_from_json(const JsonValue& value) {
    const auto& object = as_object(value, "evidence bundle");
    EvidenceBundle bundle;
    bundle.schema_version = as_string(required(object, "schema_version"), "schema_version");
    bundle.contract_id = as_string(required(object, "contract_id"), "contract_id");
    bundle.session_id = as_string(required(object, "session_id"), "session_id");
    for (const auto& record : as_array(required(object, "records"), "records")) {
        bundle.records.push_back(evidence_record_from_json(record));
    }
    if (bundle.schema_version != "evidence-bundle/0.1") throw std::invalid_argument("unsupported evidence bundle schema_version");
    return bundle;
}

JsonValue settlement_payload(const VerifierResult& value, const std::string& evidence_root) {
    JsonValue::Object claims;
    for (const auto& [claim_id, claim] : value.claims) {
        claims[claim_id] = JsonValue::Object{
            {"reason_codes", strings(claim.reason_codes)},
            {"state", to_string(claim.state)},
        };
    }
    return JsonValue::Object{
        {"claims", std::move(claims)},
        {"contract_id", value.contract_id},
        {"evidence_bundle_root", evidence_root},
        {"overall", JsonValue::Object{
            {"decision", to_string(value.decision)},
            {"reason_codes", strings(value.reason_codes)},
        }},
        {"schema_version", "settlement-commitment/0.1"},
        {"session_id", value.session_id},
        {"verifier_policy_id", value.verifier_policy_id},
    };
}

std::string contract_hash(const ComputeContract& value) {
    return canonical_sha256(to_json(value));
}

std::string evidence_bundle_root(const EvidenceBundle& value) {
    return canonical_sha256(to_json(value));
}

std::string settlement_hash(const VerifierResult& value, const std::string& evidence_root) {
    return canonical_sha256(settlement_payload(value, evidence_root));
}

} // namespace north_standard
