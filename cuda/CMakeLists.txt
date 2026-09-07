include(CheckLanguage)
check_language(CUDA)

if(NOT CMAKE_CUDA_COMPILER)
    message(FATAL_ERROR "NORTH_STANDARD_BUILD_CUDA_PROBE=ON requires a CUDA compiler (nvcc)")
endif()

enable_language(CUDA)

add_executable(north-standard-cuda-probe src/probe.cu)
set_target_properties(
    north-standard-cuda-probe
    PROPERTIES
        CUDA_STANDARD 17
        CUDA_STANDARD_REQUIRED ON
        CUDA_EXTENSIONS OFF
)

target_compile_options(
    north-standard-cuda-probe
    PRIVATE
        $<$<COMPILE_LANGUAGE:CUDA>:--expt-relaxed-constexpr>
)
