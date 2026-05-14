cmake_minimum_required(VERSION 3.20)
project(trade CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Hot-path flags
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

add_compile_options(
  -Wall -Wextra -Wpedantic
  -Wshadow -Wnon-virtual-dtor -Wold-style-cast
  -Wcast-align -Wunused -Woverloaded-virtual
  -Wconversion -Wsign-conversion
)

if(CMAKE_BUILD_TYPE STREQUAL "Release")
  add_compile_options(-O3 -march=native -fno-plt -flto)
  add_link_options(-flto)
endif()

# Conan-managed deps live here once conan install --build=missing runs.
list(APPEND CMAKE_PREFIX_PATH "${CMAKE_BINARY_DIR}")

enable_testing()
add_subdirectory(services/cpp)
