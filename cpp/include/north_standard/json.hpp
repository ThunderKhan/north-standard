#pragma once

#include <cstdint>
#include <map>
#include <string>
#include <string_view>
#include <utility>
#include <variant>
#include <vector>

namespace north_standard {

struct JsonValue {
    using Array = std::vector<JsonValue>;
    using Object = std::map<std::string, JsonValue>;
    using Storage = std::variant<std::nullptr_t, bool, std::int64_t, double, std::string, Array, Object>;

    Storage value{nullptr};

    JsonValue() = default;
    JsonValue(std::nullptr_t) : value(nullptr) {}
    JsonValue(bool v) : value(v) {}
    JsonValue(std::int64_t v) : value(v) {}
    JsonValue(int v) : value(static_cast<std::int64_t>(v)) {}
    JsonValue(double v) : value(v) {}
    JsonValue(std::string v) : value(std::move(v)) {}
    JsonValue(const char* v) : value(std::string{v}) {}
    JsonValue(Array v) : value(std::move(v)) {}
    JsonValue(Object v) : value(std::move(v)) {}
};

[[nodiscard]] JsonValue parse_json(std::string_view input);
[[nodiscard]] std::string canonical_json(const JsonValue& value);
[[nodiscard]] std::string sha256_hex(std::string_view input);
[[nodiscard]] std::string canonical_sha256(const JsonValue& value);

} // namespace north_standard
