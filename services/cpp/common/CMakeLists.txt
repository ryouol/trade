add_library(trade_common INTERFACE)

target_include_directories(trade_common INTERFACE
  ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_features(trade_common INTERFACE cxx_std_17)
