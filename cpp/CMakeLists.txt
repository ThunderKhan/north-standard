add_library(north_standard_verifier
    src/json.cpp
    src/wire.cpp
    src/verifier.cpp
    src/scenarios.cpp
)

target_include_directories(north_standard_verifier
    PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_features(north_standard_verifier PUBLIC cxx_std_20)

if(MSVC)
    target_compile_options(north_standard_verifier PRIVATE /W4 /permissive-)
else()
    target_compile_options(north_standard_verifier PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
endif()

add_executable(north-standard-cpp src/cli.cpp)
target_link_libraries(north-standard-cpp PRIVATE north_standard_verifier)

if(BUILD_TESTING)
    add_executable(north-standard-cpp-tests tests/verifier_tests.cpp)
    target_link_libraries(north-standard-cpp-tests PRIVATE north_standard_verifier)
    add_test(NAME north-standard-cpp-tests COMMAND north-standard-cpp-tests)

    add_executable(north-standard-json-tests tests/json_tests.cpp)
    target_link_libraries(north-standard-json-tests PRIVATE north_standard_verifier)
    add_test(NAME north-standard-json-tests COMMAND north-standard-json-tests)
endif()
