cmake_minimum_required(VERSION 3.20)
project(north_standard LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(
    NORTH_STANDARD_BUILD_CUDA_PROBE
    "Build the optional recorded-real CUDA probe (requires a CUDA toolkit)"
    OFF
)

include(CTest)
add_subdirectory(cpp)

if(NORTH_STANDARD_BUILD_CUDA_PROBE)
    add_subdirectory(cuda)
endif()
