#include "north_standard/json.hpp"

#include <array>
#include <bit>
#include <charconv>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <system_error>
#include <type_traits>

namespace north_standard {
namespace {

class Parser {
public:
    explicit Parser(std::string_view input) : input_(input) {}

    JsonValue parse() {
        skip_ws();
        JsonValue out = parse_value();
        skip_ws();
        if (pos_ != input_.size()) {
            fail("trailing data");
        }
        return out;
    }

private:
    std::string_view input_;
    std::size_t pos_{};

    [[noreturn]] void fail(const char* message) const {
        throw std::invalid_argument(std::string{"invalid JSON at byte "} + std::to_string(pos_) + ": " + message);
    }

    void skip_ws() {
        while (pos_ < input_.size()) {
            const char c = input_[pos_];
            if (c == ' ' || c == '\n' || c == '\r' || c == '\t') {
                ++pos_;
            } else {
                break;
            }
        }
    }

    char take() {
        if (pos_ >= input_.size()) fail("unexpected end of input");
        return input_[pos_++];
    }

    bool consume(std::string_view token) {
        if (input_.substr(pos_, token.size()) != token) return false;
        pos_ += token.size();
        return true;
    }

    JsonValue parse_value() {
        if (pos_ >= input_.size()) fail("expected value");
        switch (input_[pos_]) {
            case 'n':
                if (!consume("null")) fail("expected null");
                return JsonValue{nullptr};
            case 't':
                if (!consume("true")) fail("expected true");
                return JsonValue{true};
            case 'f':
                if (!consume("false")) fail("expected false");
                return JsonValue{false};
            case '"': return JsonValue{parse_string()};
            case '[': return JsonValue{parse_array()};
            case '{': return JsonValue{parse_object()};
            default:
                if (input_[pos_] == '-' || (input_[pos_] >= '0' && input_[pos_] <= '9')) {
                    return parse_number();
                }
                fail("expected value");
        }
    }

    static void append_utf8(std::string& out, std::uint32_t cp) {
        if (cp <= 0x7fU) {
            out.push_back(static_cast<char>(cp));
        } else if (cp <= 0x7ffU) {
            out.push_back(static_cast<char>(0xc0U | (cp >> 6U)));
            out.push_back(static_cast<char>(0x80U | (cp & 0x3fU)));
        } else if (cp <= 0xffffU) {
            out.push_back(static_cast<char>(0xe0U | (cp >> 12U)));
            out.push_back(static_cast<char>(0x80U | ((cp >> 6U) & 0x3fU)));
            out.push_back(static_cast<char>(0x80U | (cp & 0x3fU)));
        } else if (cp <= 0x10ffffU) {
            out.push_back(static_cast<char>(0xf0U | (cp >> 18U)));
            out.push_back(static_cast<char>(0x80U | ((cp >> 12U) & 0x3fU)));
            out.push_back(static_cast<char>(0x80U | ((cp >> 6U) & 0x3fU)));
            out.push_back(static_cast<char>(0x80U | (cp & 0x3fU)));
        } else {
            throw std::invalid_argument("invalid Unicode code point");
        }
    }

    std::uint32_t parse_hex4() {
        if (pos_ + 4 > input_.size()) fail("truncated unicode escape");
        std::uint32_t value = 0;
        for (int i = 0; i < 4; ++i) {
            const char c = input_[pos_++];
            value <<= 4U;
            if (c >= '0' && c <= '9') value |= static_cast<std::uint32_t>(c - '0');
            else if (c >= 'a' && c <= 'f') value |= static_cast<std::uint32_t>(10 + c - 'a');
            else if (c >= 'A' && c <= 'F') value |= static_cast<std::uint32_t>(10 + c - 'A');
            else fail("invalid unicode escape");
        }
        return value;
    }

    std::string parse_string() {
        if (take() != '"') fail("expected string");
        std::string out;
        while (pos_ < input_.size()) {
            const unsigned char c = static_cast<unsigned char>(take());
            if (c == '"') return out;
            if (c < 0x20U) fail("unescaped control character");
            if (c != '\\') {
                out.push_back(static_cast<char>(c));
                continue;
            }
            const char esc = take();
            switch (esc) {
                case '"': out.push_back('"'); break;
                case '\\': out.push_back('\\'); break;
                case '/': out.push_back('/'); break;
                case 'b': out.push_back('\b'); break;
                case 'f': out.push_back('\f'); break;
                case 'n': out.push_back('\n'); break;
                case 'r': out.push_back('\r'); break;
                case 't': out.push_back('\t'); break;
                case 'u': {
                    std::uint32_t cp = parse_hex4();
                    if (cp >= 0xd800U && cp <= 0xdbffU) {
                        if (!consume("\\u")) fail("expected low surrogate");
                        const std::uint32_t low = parse_hex4();
                        if (low < 0xdc00U || low > 0xdfffU) fail("invalid low surrogate");
                        cp = 0x10000U + ((cp - 0xd800U) << 10U) + (low - 0xdc00U);
                    } else if (cp >= 0xdc00U && cp <= 0xdfffU) {
                        fail("unexpected low surrogate");
                    }
                    append_utf8(out, cp);
                    break;
                }
                default: fail("invalid escape");
            }
        }
        fail("unterminated string");
    }

    JsonValue::Array parse_array() {
        if (take() != '[') fail("expected array");
        JsonValue::Array out;
        skip_ws();
        if (pos_ < input_.size() && input_[pos_] == ']') {
            ++pos_;
            return out;
        }
        while (true) {
            skip_ws();
            out.push_back(parse_value());
            skip_ws();
            const char c = take();
            if (c == ']') return out;
            if (c != ',') fail("expected comma or ]");
        }
    }

    JsonValue::Object parse_object() {
        if (take() != '{') fail("expected object");
        JsonValue::Object out;
        skip_ws();
        if (pos_ < input_.size() && input_[pos_] == '}') {
            ++pos_;
            return out;
        }
        while (true) {
            skip_ws();
            if (pos_ >= input_.size() || input_[pos_] != '"') fail("expected object key");
            std::string key = parse_string();
            skip_ws();
            if (take() != ':') fail("expected colon");
            skip_ws();
            auto [it, inserted] = out.emplace(std::move(key), parse_value());
            (void)it;
            if (!inserted) fail("duplicate object key");
            skip_ws();
            const char c = take();
            if (c == '}') return out;
            if (c != ',') fail("expected comma or }");
        }
    }

    JsonValue parse_number() {
        const std::size_t start = pos_;
        if (input_[pos_] == '-') ++pos_;
        if (pos_ >= input_.size()) fail("truncated number");
        if (input_[pos_] == '0') {
            ++pos_;
        } else if (input_[pos_] >= '1' && input_[pos_] <= '9') {
            while (pos_ < input_.size() && input_[pos_] >= '0' && input_[pos_] <= '9') ++pos_;
        } else {
            fail("invalid number");
        }

        bool is_float = false;
        if (pos_ < input_.size() && input_[pos_] == '.') {
            is_float = true;
            ++pos_;
            const std::size_t digits = pos_;
            while (pos_ < input_.size() && input_[pos_] >= '0' && input_[pos_] <= '9') ++pos_;
            if (digits == pos_) fail("fraction requires digits");
        }
        if (pos_ < input_.size() && (input_[pos_] == 'e' || input_[pos_] == 'E')) {
            is_float = true;
            ++pos_;
            if (pos_ < input_.size() && (input_[pos_] == '+' || input_[pos_] == '-')) ++pos_;
            const std::size_t digits = pos_;
            while (pos_ < input_.size() && input_[pos_] >= '0' && input_[pos_] <= '9') ++pos_;
            if (digits == pos_) fail("exponent requires digits");
        }

        const std::string_view token = input_.substr(start, pos_ - start);
        if (!is_float) {
            std::int64_t value{};
            const auto [ptr, ec] = std::from_chars(token.data(), token.data() + token.size(), value);
            if (ec == std::errc{} && ptr == token.data() + token.size()) return JsonValue{value};
        }

        double value{};
        const auto [ptr, ec] = std::from_chars(token.data(), token.data() + token.size(), value, std::chars_format::general);
        if (ec != std::errc{} || ptr != token.data() + token.size() || !std::isfinite(value)) {
            fail("number outside supported finite range");
        }
        return JsonValue{value};
    }
};

void append_string(std::string& out, std::string_view value) {
    static constexpr char hex[] = "0123456789abcdef";
    out.push_back('"');
    for (const unsigned char c : value) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (c < 0x20U) {
                    out += "\\u00";
                    out.push_back(hex[(c >> 4U) & 0x0fU]);
                    out.push_back(hex[c & 0x0fU]);
                } else {
                    out.push_back(static_cast<char>(c));
                }
        }
    }
    out.push_back('"');
}

std::string format_double(double value) {
    if (!std::isfinite(value)) throw std::invalid_argument("canonical JSON forbids NaN/Infinity");
    if (value == 0.0) return std::signbit(value) ? "-0.0" : "0.0";

    std::array<char, 128> buffer{};
    const auto [ptr, ec] = std::to_chars(
        buffer.data(), buffer.data() + buffer.size(), value, std::chars_format::general
    );
    if (ec != std::errc{}) throw std::runtime_error("double formatting failed");
    std::string raw(buffer.data(), ptr);

    std::string sign;
    if (!raw.empty() && raw.front() == '-') {
        sign = "-";
        raw.erase(raw.begin());
    }

    std::string digits;
    int exponent = 0;
    const auto epos = raw.find_first_of("eE");
    if (epos != std::string::npos) {
        const std::string mantissa = raw.substr(0, epos);
        const std::string exp_text = raw.substr(epos + 1);
        exponent = std::stoi(exp_text);
        for (const char c : mantissa) {
            if (c != '.') digits.push_back(c);
        }
    } else {
        const auto dot = raw.find('.');
        const std::size_t decimal_pos = dot == std::string::npos ? raw.size() : dot;
        std::string compact;
        compact.reserve(raw.size());
        for (const char c : raw) {
            if (c != '.') compact.push_back(c);
        }
        const auto first = compact.find_first_not_of('0');
        if (first == std::string::npos) return sign + "0.0";
        exponent = static_cast<int>(decimal_pos) - static_cast<int>(first) - 1;
        digits = compact.substr(first);
    }

    if (exponent < -4 || exponent >= 16) {
        std::string out = sign;
        out.push_back(digits.front());
        if (digits.size() > 1) {
            out.push_back('.');
            out.append(digits.begin() + 1, digits.end());
        }
        out.push_back('e');
        out.push_back(exponent < 0 ? '-' : '+');
        const int abs_exp = exponent < 0 ? -exponent : exponent;
        if (abs_exp < 10) out.push_back('0');
        out += std::to_string(abs_exp);
        return out;
    }

    const int decimal_index = exponent + 1;
    std::string out = sign;
    if (decimal_index <= 0) {
        out += "0.";
        out.append(static_cast<std::size_t>(-decimal_index), '0');
        out += digits;
    } else if (decimal_index >= static_cast<int>(digits.size())) {
        out += digits;
        out.append(static_cast<std::size_t>(decimal_index - static_cast<int>(digits.size())), '0');
        out += ".0";
    } else {
        out.append(digits.begin(), digits.begin() + decimal_index);
        out.push_back('.');
        out.append(digits.begin() + decimal_index, digits.end());
    }
    return out;
}

void append_json(std::string& out, const JsonValue& json) {
    std::visit([&out](const auto& value) {
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, std::nullptr_t>) {
            out += "null";
        } else if constexpr (std::is_same_v<T, bool>) {
            out += value ? "true" : "false";
        } else if constexpr (std::is_same_v<T, std::int64_t>) {
            std::array<char, 32> buffer{};
            const auto [ptr, ec] = std::to_chars(buffer.data(), buffer.data() + buffer.size(), value);
            if (ec != std::errc{}) throw std::runtime_error("integer formatting failed");
            out.append(buffer.data(), ptr);
        } else if constexpr (std::is_same_v<T, double>) {
            out += format_double(value);
        } else if constexpr (std::is_same_v<T, std::string>) {
            append_string(out, value);
        } else if constexpr (std::is_same_v<T, JsonValue::Array>) {
            out.push_back('[');
            for (std::size_t i = 0; i < value.size(); ++i) {
                if (i) out.push_back(',');
                append_json(out, value[i]);
            }
            out.push_back(']');
        } else if constexpr (std::is_same_v<T, JsonValue::Object>) {
            out.push_back('{');
            std::size_t i = 0;
            for (const auto& [key, item] : value) {
                if (i++) out.push_back(',');
                append_string(out, key);
                out.push_back(':');
                append_json(out, item);
            }
            out.push_back('}');
        }
    }, json.value);
}

constexpr std::array<std::uint32_t, 64> K{
    0x428a2f98U,0x71374491U,0xb5c0fbcfU,0xe9b5dba5U,0x3956c25bU,0x59f111f1U,0x923f82a4U,0xab1c5ed5U,
    0xd807aa98U,0x12835b01U,0x243185beU,0x550c7dc3U,0x72be5d74U,0x80deb1feU,0x9bdc06a7U,0xc19bf174U,
    0xe49b69c1U,0xefbe4786U,0x0fc19dc6U,0x240ca1ccU,0x2de92c6fU,0x4a7484aaU,0x5cb0a9dcU,0x76f988daU,
    0x983e5152U,0xa831c66dU,0xb00327c8U,0xbf597fc7U,0xc6e00bf3U,0xd5a79147U,0x06ca6351U,0x14292967U,
    0x27b70a85U,0x2e1b2138U,0x4d2c6dfcU,0x53380d13U,0x650a7354U,0x766a0abbU,0x81c2c92eU,0x92722c85U,
    0xa2bfe8a1U,0xa81a664bU,0xc24b8b70U,0xc76c51a3U,0xd192e819U,0xd6990624U,0xf40e3585U,0x106aa070U,
    0x19a4c116U,0x1e376c08U,0x2748774cU,0x34b0bcb5U,0x391c0cb3U,0x4ed8aa4aU,0x5b9cca4fU,0x682e6ff3U,
    0x748f82eeU,0x78a5636fU,0x84c87814U,0x8cc70208U,0x90befffaU,0xa4506cebU,0xbef9a3f7U,0xc67178f2U
};

constexpr std::uint32_t rotr(std::uint32_t x, unsigned n) noexcept { return (x >> n) | (x << (32U - n)); }

} // namespace

JsonValue parse_json(std::string_view input) { return Parser{input}.parse(); }

std::string canonical_json(const JsonValue& value) {
    std::string out;
    append_json(out, value);
    return out;
}

std::string sha256_hex(std::string_view input) {
    std::vector<std::uint8_t> data(input.begin(), input.end());
    const std::uint64_t bit_len = static_cast<std::uint64_t>(data.size()) * 8U;
    data.push_back(0x80U);
    while ((data.size() % 64U) != 56U) data.push_back(0U);
    for (int shift = 56; shift >= 0; shift -= 8) data.push_back(static_cast<std::uint8_t>((bit_len >> shift) & 0xffU));

    std::array<std::uint32_t, 8> h{
        0x6a09e667U,0xbb67ae85U,0x3c6ef372U,0xa54ff53aU,
        0x510e527fU,0x9b05688cU,0x1f83d9abU,0x5be0cd19U
    };

    for (std::size_t offset = 0; offset < data.size(); offset += 64U) {
        std::array<std::uint32_t, 64> w{};
        for (std::size_t i = 0; i < 16; ++i) {
            const std::size_t j = offset + i * 4U;
            w[i] = (static_cast<std::uint32_t>(data[j]) << 24U) |
                   (static_cast<std::uint32_t>(data[j + 1]) << 16U) |
                   (static_cast<std::uint32_t>(data[j + 2]) << 8U) |
                   static_cast<std::uint32_t>(data[j + 3]);
        }
        for (std::size_t i = 16; i < 64; ++i) {
            const std::uint32_t s0 = rotr(w[i-15], 7U) ^ rotr(w[i-15], 18U) ^ (w[i-15] >> 3U);
            const std::uint32_t s1 = rotr(w[i-2], 17U) ^ rotr(w[i-2], 19U) ^ (w[i-2] >> 10U);
            w[i] = w[i-16] + s0 + w[i-7] + s1;
        }

        std::uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],hh=h[7];
        for (std::size_t i = 0; i < 64; ++i) {
            const std::uint32_t S1 = rotr(e,6U)^rotr(e,11U)^rotr(e,25U);
            const std::uint32_t ch = (e & f) ^ ((~e) & g);
            const std::uint32_t temp1 = hh + S1 + ch + K[i] + w[i];
            const std::uint32_t S0 = rotr(a,2U)^rotr(a,13U)^rotr(a,22U);
            const std::uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
            const std::uint32_t temp2 = S0 + maj;
            hh=g; g=f; f=e; e=d+temp1; d=c; c=b; b=a; a=temp1+temp2;
        }
        h[0]+=a; h[1]+=b; h[2]+=c; h[3]+=d; h[4]+=e; h[5]+=f; h[6]+=g; h[7]+=hh;
    }

    static constexpr char hex[] = "0123456789abcdef";
    std::string out;
    out.reserve(64);
    for (const auto word : h) {
        for (int shift = 28; shift >= 0; shift -= 4) out.push_back(hex[(word >> shift) & 0x0fU]);
    }
    return out;
}

std::string canonical_sha256(const JsonValue& value) { return sha256_hex(canonical_json(value)); }

} // namespace north_standard
