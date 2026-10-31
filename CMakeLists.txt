cmake_minimum_required(VERSION 3.24)

include(cmake/Version.cmake)
insidious_read_version("${CMAKE_CURRENT_SOURCE_DIR}" INSIDIOUS_SOURCE_VERSION)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/version.txt")

project(insidious
    VERSION ${INSIDIOUS_SOURCE_VERSION}
    LANGUAGES CXX
)

include(GNUInstallDirs)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_AUTOMOC ON)

include(CTest)
option(INSIDIOUS_BUILD_MEMORY_AUDIT "Build developer memory-audit tooling" OFF)

find_package(Qt6 6.6 REQUIRED COMPONENTS Core Gui Widgets Concurrent)
if(BUILD_TESTING)
    find_package(Qt6 6.6 REQUIRED COMPONENTS Test)
endif()
find_package(PkgConfig REQUIRED)
pkg_check_modules(VIPSCPP REQUIRED IMPORTED_TARGET vips-cpp>=8.18.3)
pkg_check_modules(LIBARCHIVE REQUIRED IMPORTED_TARGET libarchive)

include(cmake/BuildMetadata.cmake)

set(CORE_SOURCES
    src/core/app_settings.cpp
    src/core/app_settings.h
    src/core/archive_entry_stream.cpp
    src/core/archive_entry_stream.h
    src/core/archive_collection_source.cpp
    src/core/archive_collection_source.h
    src/core/decoded_image.h
    src/core/folder_collection_source.cpp
    src/core/folder_collection_source.h
    src/core/image_entry.cpp
    src/core/image_entry.h
    src/core/image_entry_validation.cpp
    src/core/image_entry_validation.h
    src/core/image_formats.cpp
    src/core/image_formats.h
    src/core/image_sort.cpp
    src/core/image_sort.h
    src/core/memory_image_cache.cpp
    src/core/memory_image_cache.h
    src/core/multi_collection_source.cpp
    src/core/multi_collection_source.h
    src/core/natural_sort.cpp
    src/core/natural_sort.h
    src/core/render_memory_budget.cpp
    src/core/render_memory_budget.h
    src/core/vips_image_decoder.cpp
    src/core/vips_image_decoder.h
    src/core/viewer_controller.cpp
    src/core/viewer_controller.h
)

add_library(insidious_core STATIC ${CORE_SOURCES})
target_include_directories(insidious_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(insidious_core
    PUBLIC
        Qt6::Core
        Qt6::Gui
        Qt6::Concurrent
        PkgConfig::VIPSCPP
        PkgConfig::LIBARCHIVE
)

set(UI_SOURCES
    src/ui/about_dialog.cpp
    src/ui/about_dialog.h
    src/ui/collection_tree_model.cpp
    src/ui/collection_tree_model.h
    src/ui/comparison_drag_mime_data.cpp
    src/ui/comparison_drag_mime_data.h
    src/ui/comparison_view_widget.cpp
    src/ui/comparison_view_widget.h
    src/ui/image_info_panel.cpp
    src/ui/image_info_panel.h
    src/ui/image_list_model.cpp
    src/ui/image_list_model.h
    src/ui/image_view_widget.cpp
    src/ui/image_view_widget.h
    src/ui/main_window.cpp
    src/ui/main_window.h
    src/ui/quick_jump_dialog.cpp
    src/ui/quick_jump_dialog.h
    src/ui/settings_dialog.cpp
    src/ui/settings_dialog.h
    src/ui/status_line_formatter.cpp
    src/ui/status_line_formatter.h
    src/ui/thumbnail_list_model.cpp
    src/ui/thumbnail_list_model.h
    src/ui/thumbnail_loader.cpp
    src/ui/thumbnail_loader.h
)
add_executable(insidious src/app/main.cpp ${UI_SOURCES})
qt_add_resources(DESKTOP_RESOURCES resources/insidious.qrc)
target_sources(insidious PRIVATE ${DESKTOP_RESOURCES})
target_link_libraries(insidious
    PRIVATE
        insidious_core
        Qt6::Widgets
)
target_link_libraries(insidious PRIVATE insidious_version)

install(TARGETS insidious
    RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}"
)
install(FILES resources/io.github._0xf836.Insidious.desktop
    DESTINATION "${CMAKE_INSTALL_DATAROOTDIR}/applications")
install(FILES resources/io.github._0xf836.Insidious.metainfo.xml
    DESTINATION "${CMAKE_INSTALL_DATAROOTDIR}/metainfo")
install(DIRECTORY resources/icons/
    DESTINATION "${CMAKE_INSTALL_DATAROOTDIR}/icons/hicolor"
    FILES_MATCHING PATTERN "*.svg" PATTERN "*.png")
install(FILES
    README.md
    LICENSE
    PKGBUILD
    version.txt
    DESTINATION "${CMAKE_INSTALL_DOCDIR}"
)
install(DIRECTORY docs/
    DESTINATION "${CMAKE_INSTALL_DOCDIR}/docs"
)
install(FILES LICENSE
    DESTINATION "${CMAKE_INSTALL_DATAROOTDIR}/licenses/${PROJECT_NAME}"
)

if(INSIDIOUS_BUILD_MEMORY_AUDIT)
add_executable(insidious_memory_audit
    tools/memory_audit.cpp
)
target_link_libraries(insidious_memory_audit
    PRIVATE
        insidious_core
)

endif()

if(BUILD_TESTING)

find_program(DESKTOP_FILE_VALIDATE desktop-file-validate)
find_program(APPSTREAMCLI appstreamcli)
add_test(NAME insidious_desktop_install_tests
    COMMAND "${CMAKE_COMMAND}" "-DBUILD_DIR=${CMAKE_BINARY_DIR}"
        "-DSTAGE=${CMAKE_BINARY_DIR}/desktop-install-test"
        "-DDESKTOP_VALIDATOR=${DESKTOP_FILE_VALIDATE}"
        "-DAPPSTREAM_VALIDATOR=${APPSTREAMCLI}"
        -P "${CMAKE_SOURCE_DIR}/tests/desktop_install_tests.cmake")
find_package(Python3 QUIET COMPONENTS Interpreter)
if(Python3_Interpreter_FOUND)
    add_test(NAME insidious_packaging_tests
        COMMAND "${Python3_EXECUTABLE}" -m unittest discover
            -s "${CMAKE_SOURCE_DIR}/tests" -p packaging_tests.py -v)
    add_test(NAME insidious_release_tests
        COMMAND "${Python3_EXECUTABLE}" -m unittest discover
            -s "${CMAKE_SOURCE_DIR}/tests" -p release_tests.py -v)
endif()

add_executable(insidious_core_tests
    tests/core_tests.cpp
)
target_link_libraries(insidious_core_tests
    PRIVATE
        insidious_core
        Qt6::Test
)
add_test(NAME insidious_core_tests COMMAND insidious_core_tests)
set_tests_properties(insidious_core_tests PROPERTIES
    ENVIRONMENT "QT_QPA_PLATFORM=offscreen"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/tests"
)

add_executable(insidious_ui_tests
    tests/status_line_formatter_tests.cpp
    src/ui/status_line_formatter.cpp
    src/ui/status_line_formatter.h
)
target_link_libraries(insidious_ui_tests
    PRIVATE
        insidious_core
        Qt6::Test
        Qt6::Widgets
)
add_test(NAME insidious_ui_tests COMMAND insidious_ui_tests)
set_tests_properties(insidious_ui_tests PROPERTIES
    ENVIRONMENT "QT_QPA_PLATFORM=offscreen"
)

add_executable(insidious_comparison_view_widget_tests
    tests/comparison_view_widget_tests.cpp
    src/ui/comparison_drag_mime_data.cpp
    src/ui/comparison_drag_mime_data.h
    src/ui/comparison_view_widget.cpp
    src/ui/comparison_view_widget.h
)
target_link_libraries(insidious_comparison_view_widget_tests
    PRIVATE
        insidious_core
        Qt6::Test
        Qt6::Widgets
        Qt6::Concurrent
)
add_test(NAME insidious_comparison_view_widget_tests COMMAND insidious_comparison_view_widget_tests)
set_tests_properties(insidious_comparison_view_widget_tests PROPERTIES
    ENVIRONMENT "QT_QPA_PLATFORM=offscreen"
)

add_executable(insidious_thumbnail_list_model_tests
    tests/thumbnail_list_model_tests.cpp
    src/ui/thumbnail_list_model.cpp
    src/ui/thumbnail_list_model.h
)
target_link_libraries(insidious_thumbnail_list_model_tests
    PRIVATE
        insidious_core
        Qt6::Test
        Qt6::Widgets
)
add_test(NAME insidious_thumbnail_list_model_tests COMMAND insidious_thumbnail_list_model_tests)
set_tests_properties(insidious_thumbnail_list_model_tests PROPERTIES
    ENVIRONMENT "QT_QPA_PLATFORM=offscreen"
)

add_executable(insidious_settings_dialog_tests
    tests/settings_dialog_tests.cpp
    src/ui/settings_dialog.cpp
    src/ui/settings_dialog.h
)
target_link_libraries(insidious_settings_dialog_tests
    PRIVATE
        insidious_core
        Qt6::Test
        Qt6::Widgets
)
add_test(NAME insidious_settings_dialog_tests COMMAND insidious_settings_dialog_tests)
set_tests_properties(insidious_settings_dialog_tests PROPERTIES
    ENVIRONMENT "QT_QPA_PLATFORM=offscreen"
)

add_executable(insidious_image_view_widget_tests
    tests/image_view_widget_tests.cpp
    src/ui/image_view_widget.cpp
    src/ui/image_view_widget.h
)
target_link_libraries(insidious_image_view_widget_tests
    PRIVATE
        insidious_core
        Qt6::Test
        Qt6::Widgets
)
add_test(NAME insidious_image_view_widget_tests COMMAND insidious_image_view_widget_tests)
set_tests_properties(insidious_image_view_widget_tests PROPERTIES
    ENVIRONMENT "QT_QPA_PLATFORM=offscreen"
)
add_test(NAME insidious_image_view_widget_hidpi_tests COMMAND insidious_image_view_widget_tests)
set_tests_properties(insidious_image_view_widget_hidpi_tests PROPERTIES
    ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_SCALE_FACTOR=2;INSIDIOUS_EXPECT_HIDPI=1"
)

add_executable(insidious_collection_tree_model_tests
    tests/collection_tree_model_tests.cpp
    src/ui/collection_tree_model.cpp
    src/ui/collection_tree_model.h
)
target_link_libraries(insidious_collection_tree_model_tests
    PRIVATE
        insidious_core
        Qt6::Test
        Qt6::Widgets
)
add_test(NAME insidious_collection_tree_model_tests COMMAND insidious_collection_tree_model_tests)
set_tests_properties(insidious_collection_tree_model_tests PROPERTIES
    ENVIRONMENT "QT_QPA_PLATFORM=offscreen"
)

add_executable(insidious_main_window_async_tests
    tests/main_window_async_tests.cpp
    ${UI_SOURCES}
)
target_sources(insidious_main_window_async_tests PRIVATE ${DESKTOP_RESOURCES})
target_link_libraries(insidious_main_window_async_tests PRIVATE insidious_core Qt6::Widgets Qt6::Test insidious_version)
add_test(NAME insidious_main_window_async_tests COMMAND insidious_main_window_async_tests)
set_tests_properties(insidious_main_window_async_tests PROPERTIES
    ENVIRONMENT "QT_QPA_PLATFORM=offscreen"
    TIMEOUT 30
)

add_test(NAME insidious_version_metadata_tests
    COMMAND "${CMAKE_COMMAND}" "-DPROJECT_ROOT=${CMAKE_CURRENT_SOURCE_DIR}"
        "-DTEST_ROOT=${CMAKE_CURRENT_BINARY_DIR}/version-metadata-tests"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/version_metadata_tests.cmake")
add_test(NAME insidious_headless_version_tests
    COMMAND "${CMAKE_COMMAND}" "-DAPP=$<TARGET_FILE:insidious>"
        "-DHEADER=${VERSION_OUTPUT_DIR}/build_version.h"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/headless_version_tests.cmake")

endif()
