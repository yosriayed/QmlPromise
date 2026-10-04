find_package(Qt6 REQUIRED COMPONENTS Gui Quick QuickControls2 Concurrent)

if(Qt6_VERSION VERSION_GREATER_EQUAL "6.8")
    qt_policy(SET QTP0004 NEW)
endif()
qt_standard_project_setup(REQUIRES 6.5)

qt_add_executable(appQmlPromiseDemo
    src/main.cpp
)

target_include_directories(appQmlPromiseDemo PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)

qt_add_qml_module(appQmlPromiseDemo
    URI QmlPromiseDemo
    VERSION 1.0
    SOURCES
        src/backend.h
        src/backend.cpp
    QML_FILES
        qml/Main.qml
)

target_link_libraries(appQmlPromiseDemo PRIVATE
    QmlPromise::QmlPromise
    Qt6::Gui
    Qt6::Quick
    Qt6::Concurrent
    Qt6::QuickControls2
)
