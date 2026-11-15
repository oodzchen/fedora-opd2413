cmake_minimum_required(VERSION 3.20)
project(opd2413faceqml LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 REQUIRED COMPONENTS Core DBus Qml)

add_library(opd2413faceqml SHARED
    facebridge.h
    facebridge.cpp
)

set_target_properties(opd2413faceqml PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/org/opd2413/face"
)

target_link_libraries(opd2413faceqml PRIVATE
    Qt6::Core
    Qt6::DBus
    Qt6::Qml
)

if(NOT DEFINED QML_INSTALL_DIR)
    set(QML_INSTALL_DIR "lib64/qt6/qml")
endif()

install(TARGETS opd2413faceqml
    LIBRARY DESTINATION "${QML_INSTALL_DIR}/org/opd2413/face"
)
install(FILES qmldir
    DESTINATION "${QML_INSTALL_DIR}/org/opd2413/face"
)
