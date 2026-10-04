cmake_minimum_required(VERSION 3.20)
project(QmlPromise VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Determine if QmlPromise is built as the top-level project or included via FetchContent/add_subdirectory
if(CMAKE_PROJECT_NAME STREQUAL PROJECT_NAME)
    set(QMLPROMISE_IS_TOP_LEVEL ON)
else()
    set(QMLPROMISE_IS_TOP_LEVEL OFF)
endif()

option(QMLPROMISE_BUILD_DEMO "Build QmlPromise demo application" ${QMLPROMISE_IS_TOP_LEVEL})
option(QMLPROMISE_BUILD_TESTS "Build QmlPromise unit tests" ${QMLPROMISE_IS_TOP_LEVEL})
option(QMLPROMISE_INSTALL "Generate install targets for QmlPromise" ${QMLPROMISE_IS_TOP_LEVEL})

# Required Qt dependencies for the library interface
find_package(Qt6 REQUIRED COMPONENTS Core Qml)

# Define the INTERFACE library target
add_library(QmlPromise INTERFACE)
add_library(QmlPromise::QmlPromise ALIAS QmlPromise)

target_include_directories(QmlPromise INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)

target_compile_features(QmlPromise INTERFACE cxx_std_20)

target_link_libraries(QmlPromise INTERFACE
    Qt6::Core
    Qt6::Qml
)

# -----------------------------------------------------------------------------
# Optional Example Application
# -----------------------------------------------------------------------------
if(QMLPROMISE_BUILD_DEMO)
    add_subdirectory(demo)
endif()

# -----------------------------------------------------------------------------
# Optional Automated Unit Tests
# -----------------------------------------------------------------------------
if(QMLPROMISE_BUILD_TESTS)
    find_package(Qt6 REQUIRED COMPONENTS Test Concurrent)
    enable_testing()
    add_executable(tst_qml_promise tests/test_qml_promise.cpp)
    set_target_properties(tst_qml_promise PROPERTIES AUTOMOC ON)
    target_link_libraries(tst_qml_promise PRIVATE
        QmlPromise::QmlPromise
        Qt6::Concurrent
        Qt6::Test
    )
    add_test(NAME tst_qml_promise COMMAND tst_qml_promise)
endif()

# -----------------------------------------------------------------------------
# Installation & CMake Export Targets
# -----------------------------------------------------------------------------
if(QMLPROMISE_INSTALL)
    include(GNUInstallDirs)
    include(CMakePackageConfigHelpers)

    install(TARGETS QmlPromise
        EXPORT QmlPromiseTargets
        INCLUDES DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
    )

    install(DIRECTORY include/
        DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
    )

    install(EXPORT QmlPromiseTargets
        FILE QmlPromiseTargets.cmake
        NAMESPACE QmlPromise::
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/QmlPromise
    )

    configure_package_config_file(
        cmake/QmlPromiseConfig.cmake.in
        ${CMAKE_CURRENT_BINARY_DIR}/QmlPromiseConfig.cmake
        INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/QmlPromise
    )

    write_basic_package_version_file(
        ${CMAKE_CURRENT_BINARY_DIR}/QmlPromiseConfigVersion.cmake
        VERSION ${PROJECT_VERSION}
        COMPATIBILITY SameMajorVersion
    )

    install(FILES
        ${CMAKE_CURRENT_BINARY_DIR}/QmlPromiseConfig.cmake
        ${CMAKE_CURRENT_BINARY_DIR}/QmlPromiseConfigVersion.cmake
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/QmlPromise
    )
endif()
