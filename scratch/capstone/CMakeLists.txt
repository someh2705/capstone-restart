find_package(PkgConfig REQUIRED)

pkg_check_modules(PC_YAML_CPP REQUIRED yaml-cpp)

# Create a custom library
add_library(
  capstone-lib
  lib/scenario-spec.h
  lib/scenario-loader.h
  lib/scenario-loader.cc
  lib/amt.h
  lib/amt.cc
)

target_include_directories(
  capstone-lib
  PUBLIC ${PC_YAML_CPP_INCLUDE_DIRS}
  PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}
)

target_link_libraries(
  capstone-lib
  PUBLIC ${PC_YAML_CPP_LIBRARIES}
  PUBLIC ${ns3-libs}
  PUBLIC ${ns3-contrib-libs}
)

# Link the custom library to the scratch executable
build_exec(
  EXECNAME capstone-simulator
  SOURCE_FILES capstone-simulator.cc
  LIBRARIES_TO_LINK capstone-lib
                    ${ns3-libs}
                    ${ns3-contrib-libs}
  # use "${ns3-libs}" "${ns3-contrib-libs}" in case you want to link to all
  # enabled modules
  EXECUTABLE_DIRECTORY_PATH ${CMAKE_OUTPUT_DIRECTORY}/scratch/capstone
)
