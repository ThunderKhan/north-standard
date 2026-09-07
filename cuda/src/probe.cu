#include <cuda_runtime.h>

#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct Options {
    int device = 0;
    int warmup_iterations = 3;
    int measurement_iterations = 8;
    std::size_t elements = 4u * 1024u * 1024u;
    int compute_inner_iterations = 128;
    std::string capture_id;
    std::string contract_id = "recorded-contract";
    std::string session_id = "recorded-session";
    std::string runtime_profile_id = "CUDA-RECORDED-v0.1";
    std::string benchmark_profile_id = "CUDA-MICROBENCH-v0.1";
    std::string output_path;
};

void cuda_check(cudaError_t status, const char* expression) {
    if (status != cudaSuccess) {
        std::ostringstream message;
        message << expression << " failed: " << cudaGetErrorString(status);
        throw std::runtime_error(message.str());
    }
}

#define CUDA_CHECK(expr) cuda_check((expr), #expr)

std::int64_t unix_millis_now() {
    const auto now = std::chrono::system_clock::now().time_since_epoch();
    return std::chrono::duration_cast<std::chrono::milliseconds>(now).count();
}

std::string default_capture_id() {
    std::ostringstream out;
    out << "cuda-capture-" << unix_millis_now();
    return out.str();
}

std::string json_escape(const std::string& value) {
    std::ostringstream out;
    for (const unsigned char ch : value) {
        switch (ch) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\b': out << "\\b"; break;
            case '\f': out << "\\f"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (ch < 0x20) {
                    out << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                        << static_cast<int>(ch) << std::dec;
                } else {
                    out << static_cast<char>(ch);
                }
        }
    }
    return out.str();
}

int parse_int(const char* text, const char* name) {
    char* end = nullptr;
    const long value = std::strtol(text, &end, 10);
    if (end == text || *end != '\0') {
        throw std::runtime_error(std::string("invalid integer for ") + name);
    }
    return static_cast<int>(value);
}

std::size_t parse_size(const char* text, const char* name) {
    char* end = nullptr;
    const unsigned long long value = std::strtoull(text, &end, 10);
    if (end == text || *end != '\0' || value == 0) {
        throw std::runtime_error(std::string("invalid positive size for ") + name);
    }
    return static_cast<std::size_t>(value);
}

Options parse_options(int argc, char** argv) {
    Options options;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        auto require_value = [&](const char* name) -> const char* {
            if (i + 1 >= argc) {
                throw std::runtime_error(std::string("missing value for ") + name);
            }
            return argv[++i];
        };

        if (arg == "--device") {
            options.device = parse_int(require_value("--device"), "--device");
        } else if (arg == "--warmup") {
            options.warmup_iterations = parse_int(require_value("--warmup"), "--warmup");
        } else if (arg == "--iterations") {
            options.measurement_iterations = parse_int(require_value("--iterations"), "--iterations");
        } else if (arg == "--elements") {
            options.elements = parse_size(require_value("--elements"), "--elements");
        } else if (arg == "--inner") {
            options.compute_inner_iterations = parse_int(require_value("--inner"), "--inner");
        } else if (arg == "--capture-id") {
            options.capture_id = require_value("--capture-id");
        } else if (arg == "--contract-id") {
            options.contract_id = require_value("--contract-id");
        } else if (arg == "--session-id") {
            options.session_id = require_value("--session-id");
        } else if (arg == "--runtime-profile-id") {
            options.runtime_profile_id = require_value("--runtime-profile-id");
        } else if (arg == "--benchmark-profile-id") {
            options.benchmark_profile_id = require_value("--benchmark-profile-id");
        } else if (arg == "--output") {
            options.output_path = require_value("--output");
        } else if (arg == "--help" || arg == "-h") {
            std::cout
                << "north-standard-cuda-probe [options]\n"
                << "  --device N\n"
                << "  --warmup N\n"
                << "  --iterations N\n"
                << "  --elements N\n"
                << "  --inner N\n"
                << "  --capture-id ID\n"
                << "  --contract-id ID\n"
                << "  --session-id ID\n"
                << "  --runtime-profile-id ID\n"
                << "  --benchmark-profile-id ID\n"
                << "  --output PATH\n";
            std::exit(0);
        } else {
            throw std::runtime_error("unknown argument: " + arg);
        }
    }

    if (options.capture_id.empty()) {
        options.capture_id = default_capture_id();
    }
    if (options.warmup_iterations < 0 || options.measurement_iterations < 2) {
        throw std::runtime_error("warmup must be >= 0 and iterations must be >= 2");
    }
    if (options.compute_inner_iterations < 1) {
        throw std::runtime_error("--inner must be >= 1");
    }
    return options;
}

__global__ void compute_kernel(float* data, std::size_t count, int inner_iterations) {
    const std::size_t index = static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (index >= count) {
        return;
    }

    float value = data[index];
    for (int i = 0; i < inner_iterations; ++i) {
        value = fmaf(value, 1.000001f, 0.000001f);
    }
    data[index] = value;
}

__global__ void copy_kernel(const float* source, float* destination, std::size_t count) {
    const std::size_t index = static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (index < count) {
        destination[index] = source[index];
    }
}

float time_compute(
    float* device_data,
    std::size_t elements,
    int inner_iterations,
    int blocks,
    int threads,
    cudaEvent_t start,
    cudaEvent_t stop
) {
    CUDA_CHECK(cudaEventRecord(start));
    compute_kernel<<<blocks, threads>>>(device_data, elements, inner_iterations);
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    float elapsed_ms = 0.0f;
    CUDA_CHECK(cudaEventElapsedTime(&elapsed_ms, start, stop));
    return elapsed_ms;
}

float time_copy(
    const float* source,
    float* destination,
    std::size_t elements,
    int blocks,
    int threads,
    cudaEvent_t start,
    cudaEvent_t stop
) {
    CUDA_CHECK(cudaEventRecord(start));
    copy_kernel<<<blocks, threads>>>(source, destination, elements);
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    float elapsed_ms = 0.0f;
    CUDA_CHECK(cudaEventElapsedTime(&elapsed_ms, start, stop));
    return elapsed_ms;
}

struct Sample {
    int index{};
    std::int64_t observed_at_unix_ms{};
    double compute_ms{};
    double compute_gflops{};
    double memory_ms{};
    double memory_gbps{};
};

std::string render_json(
    const Options& options,
    const cudaDeviceProp& properties,
    int runtime_version,
    int driver_version,
    std::int64_t captured_at_unix_ms,
    const std::vector<Sample>& samples
) {
    std::ostringstream out;
    out << std::fixed << std::setprecision(6);
    out << "{\n";
    out << "  \"schema_version\": \"gpu-trace/0.1\",\n";
    out << "  \"provenance\": \"RECORDED_REAL\",\n";
    out << "  \"capture_id\": \"" << json_escape(options.capture_id) << "\",\n";
    out << "  \"captured_at_unix_ms\": " << captured_at_unix_ms << ",\n";
    out << "  \"contract_id\": \"" << json_escape(options.contract_id) << "\",\n";
    out << "  \"session_id\": \"" << json_escape(options.session_id) << "\",\n";
    out << "  \"runtime_profile_id\": \"" << json_escape(options.runtime_profile_id) << "\",\n";
    out << "  \"benchmark_profile_id\": \"" << json_escape(options.benchmark_profile_id) << "\",\n";
    out << "  \"collector\": {\n";
    out << "    \"name\": \"north-standard-cuda-probe\",\n";
    out << "    \"version\": \"0.1\",\n";
    out << "    \"authentication\": \"LOCAL_SOFTWARE_ONLY\"\n";
    out << "  },\n";
    out << "  \"device\": {\n";
    out << "    \"ordinal\": " << options.device << ",\n";
    out << "    \"name\": \"" << json_escape(properties.name) << "\",\n";
    out << "    \"compute_capability_major\": " << properties.major << ",\n";
    out << "    \"compute_capability_minor\": " << properties.minor << ",\n";
    out << "    \"global_memory_bytes\": " << properties.totalGlobalMem << ",\n";
    out << "    \"multiprocessor_count\": " << properties.multiProcessorCount << ",\n";
    out << "    \"max_clock_khz\": " << properties.clockRate << ",\n";
    out << "    \"memory_clock_khz\": " << properties.memoryClockRate << ",\n";
    out << "    \"memory_bus_width_bits\": " << properties.memoryBusWidth << ",\n";
    out << "    \"cuda_runtime_version\": " << runtime_version << ",\n";
    out << "    \"cuda_driver_version\": " << driver_version << "\n";
    out << "  },\n";
    out << "  \"challenge\": {\n";
    out << "    \"elements\": " << options.elements << ",\n";
    out << "    \"compute_inner_iterations\": " << options.compute_inner_iterations << ",\n";
    out << "    \"warmup_iterations\": " << options.warmup_iterations << ",\n";
    out << "    \"measurement_iterations\": " << options.measurement_iterations << "\n";
    out << "  },\n";
    out << "  \"samples\": [\n";
    for (std::size_t i = 0; i < samples.size(); ++i) {
        const Sample& sample = samples[i];
        out << "    {\n";
        out << "      \"sample_index\": " << sample.index << ",\n";
        out << "      \"observed_at_unix_ms\": " << sample.observed_at_unix_ms << ",\n";
        out << "      \"compute_ms\": " << sample.compute_ms << ",\n";
        out << "      \"compute_gflops\": " << sample.compute_gflops << ",\n";
        out << "      \"memory_ms\": " << sample.memory_ms << ",\n";
        out << "      \"memory_gbps\": " << sample.memory_gbps << "\n";
        out << "    }" << (i + 1 == samples.size() ? "\n" : ",\n");
    }
    out << "  ],\n";
    out << "  \"limitations\": [\n";
    out << "    \"This is local software-recorded evidence, not hardware-rooted attestation.\",\n";
    out << "    \"The microbenchmark is a research probe and is not a production GPU performance standard.\",\n";
    out << "    \"Device power and thermals are not captured by this v0.1 CUDA-runtime-only collector.\"\n";
    out << "  ]\n";
    out << "}\n";
    return out.str();
}

} // namespace

int main(int argc, char** argv) {
    try {
        const Options options = parse_options(argc, argv);
        CUDA_CHECK(cudaSetDevice(options.device));

        cudaDeviceProp properties{};
        CUDA_CHECK(cudaGetDeviceProperties(&properties, options.device));

        int runtime_version = 0;
        int driver_version = 0;
        CUDA_CHECK(cudaRuntimeGetVersion(&runtime_version));
        CUDA_CHECK(cudaDriverGetVersion(&driver_version));

        float* device_a = nullptr;
        float* device_b = nullptr;
        const std::size_t bytes = options.elements * sizeof(float);
        CUDA_CHECK(cudaMalloc(&device_a, bytes));
        CUDA_CHECK(cudaMalloc(&device_b, bytes));
        CUDA_CHECK(cudaMemset(device_a, 1, bytes));
        CUDA_CHECK(cudaMemset(device_b, 0, bytes));

        cudaEvent_t start{};
        cudaEvent_t stop{};
        CUDA_CHECK(cudaEventCreate(&start));
        CUDA_CHECK(cudaEventCreate(&stop));

        constexpr int threads = 256;
        const int blocks = static_cast<int>((options.elements + threads - 1) / threads);

        for (int i = 0; i < options.warmup_iterations; ++i) {
            (void)time_compute(
                device_a,
                options.elements,
                options.compute_inner_iterations,
                blocks,
                threads,
                start,
                stop
            );
            (void)time_copy(device_a, device_b, options.elements, blocks, threads, start, stop);
        }

        const std::int64_t captured_at_unix_ms = unix_millis_now();
        std::vector<Sample> samples;
        samples.reserve(static_cast<std::size_t>(options.measurement_iterations));

        for (int i = 0; i < options.measurement_iterations; ++i) {
            Sample sample;
            sample.index = i;
            sample.observed_at_unix_ms = unix_millis_now();
            sample.compute_ms = time_compute(
                device_a,
                options.elements,
                options.compute_inner_iterations,
                blocks,
                threads,
                start,
                stop
            );
            sample.memory_ms = time_copy(
                device_a,
                device_b,
                options.elements,
                blocks,
                threads,
                start,
                stop
            );

            const double flop_count = static_cast<double>(options.elements)
                * static_cast<double>(options.compute_inner_iterations) * 2.0;
            const double transferred_bytes = static_cast<double>(bytes) * 2.0;
            sample.compute_gflops = flop_count / (sample.compute_ms * 1.0e6);
            sample.memory_gbps = transferred_bytes / (sample.memory_ms * 1.0e6);
            samples.push_back(sample);
        }

        CUDA_CHECK(cudaEventDestroy(start));
        CUDA_CHECK(cudaEventDestroy(stop));
        CUDA_CHECK(cudaFree(device_a));
        CUDA_CHECK(cudaFree(device_b));

        const std::string json = render_json(
            options,
            properties,
            runtime_version,
            driver_version,
            captured_at_unix_ms,
            samples
        );

        if (options.output_path.empty()) {
            std::cout << json;
        } else {
            std::ofstream output(options.output_path, std::ios::binary);
            if (!output) {
                throw std::runtime_error("could not open output path: " + options.output_path);
            }
            output << json;
            std::cout << options.output_path << '\n';
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "north-standard-cuda-probe: " << error.what() << '\n';
        return 1;
    }
}
