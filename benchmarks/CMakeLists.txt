cmake_minimum_required(VERSION 3.20)
project(QmlPromiseBenchmarks LANGUAGES CXX)

find_package(Qt6 6.5 REQUIRED COMPONENTS Core Qml Concurrent)
add_executable(bench_qml_promise main.cpp)
set_target_properties(bench_qml_promise PROPERTIES AUTOMOC ON)
target_compile_features(bench_qml_promise PRIVATE cxx_std_20)
target_include_directories(bench_qml_promise PRIVATE ../include)
target_link_libraries(bench_qml_promise PRIVATE Qt6::Core Qt6::Qml Qt6::Concurrent)
