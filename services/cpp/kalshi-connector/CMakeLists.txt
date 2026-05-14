add_executable(kalshi-connector main.cpp)
target_link_libraries(kalshi-connector PRIVATE trade_common)
target_compile_features(kalshi-connector PRIVATE cxx_std_17)

# Conan-installed deps (uncomment as they become required):
# find_package(OpenSSL REQUIRED)
# find_package(Boost REQUIRED COMPONENTS system)
# find_package(spdlog REQUIRED)
# find_package(fmt REQUIRED)
# target_link_libraries(kalshi-connector PRIVATE OpenSSL::Crypto Boost::system spdlog::spdlog fmt::fmt)
