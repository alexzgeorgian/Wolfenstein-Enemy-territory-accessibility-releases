cmake_minimum_required(VERSION 3.10)
project(ETAccessibility C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

set(ETA_ACCESSIBILITY_SOURCES
    src/accessibility/audio/audio_cue_system.c
    src/accessibility/core/accessibility_runtime.c
    src/accessibility/core/debug_log.c
    src/accessibility/core/error_handler.c
    src/accessibility/core/event_router.c
    src/accessibility/core/runtime_guard.c
    src/accessibility/hud/hud_narrator.c
    src/accessibility/map/bsp_ladders.c
    src/accessibility/map/bsp_props.c
    src/accessibility/map/map_survey.c
    src/accessibility/menu/menu_narrator.c
    src/accessibility/navigation/navigation_system.c
    src/accessibility/navigation/place_classifier.c
    src/accessibility/navigation/sniper_spots.c
    src/accessibility/navigation/rooms.c
    src/accessibility/platform/windows/windows_audio_cue.c
    src/accessibility/platform/windows/windows_nvda.c
    src/accessibility/platform/windows/windows_speech.c
    src/accessibility/platform/windows/windows_update.c
    src/accessibility/speech/speech_manager.c
    src/accessibility/update/update_check.c
)

# The Mac's speech is VoiceOver and the system voice, reached through
# AppKit and AVFoundation, and its updater downloads with Foundation's
# NSURLSession: all Objective-C.
if(APPLE)
    enable_language(OBJC)
    list(APPEND ETA_ACCESSIBILITY_SOURCES
        src/accessibility/platform/macos/macos_speech.m
        src/accessibility/platform/macos/macos_update.m)
    set_source_files_properties(
        src/accessibility/platform/macos/macos_speech.m
        src/accessibility/platform/macos/macos_update.m
        PROPERTIES COMPILE_FLAGS "-fobjc-arc")
endif()

add_library(eta_accessibility STATIC ${ETA_ACCESSIBILITY_SOURCES})

target_include_directories(eta_accessibility PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/src/accessibility"
)

# Which release this is, and the ET: Legacy it was built for, so the
# in-game updater knows what it is replacing. release/build-release.sh
# passes both; anything else is a development build and never updates.
set(ETA_RELEASE_VERSION "dev" CACHE STRING "Version name of this build, e.g. beta-0.02.3")
set(ETA_ENGINE_TAG "" CACHE STRING "ET: Legacy tag this build is for, e.g. v2.86.0")
# The Mac's bots file, qagame_mac, ships beside the pk3 rather than in it,
# so the menus check the copy a player installed is the one built with
# this release. Its SHA-256, from the same build; empty skips the check.
set(ETA_MAC_GAME_SHA256 "" CACHE STRING "SHA-256 of the qagame_mac built with this release")
set_source_files_properties(src/accessibility/update/update_check.c PROPERTIES
    COMPILE_DEFINITIONS "ETA_RELEASE_VERSION=\"${ETA_RELEASE_VERSION}\";ETA_ENGINE_TAG=\"${ETA_ENGINE_TAG}\";ETA_MAC_GAME_SHA256=\"${ETA_MAC_GAME_SHA256}\"")

if(MSVC)
    target_compile_options(eta_accessibility PRIVATE /W4)
else()
    target_compile_options(eta_accessibility PRIVATE -Wall -Wextra)
endif()

if(WIN32)
    target_link_libraries(eta_accessibility PUBLIC ole32 oleaut32 winmm winhttp)
elseif(APPLE)
    target_link_libraries(eta_accessibility PUBLIC "-framework AppKit" "-framework AVFoundation" "-framework Foundation")
endif()

option(ETA_BUILD_SMOKE_TEST "Build the accessibility runtime smoke test executable" ON)

if(ETA_BUILD_SMOKE_TEST)
    add_executable(eta_accessibility_smoke_test tests/speech_smoke_test.c)
    target_link_libraries(eta_accessibility_smoke_test PRIVATE eta_accessibility)

    add_executable(eta_menu_narrator_smoke_test tests/menu_narrator_smoke_test.c)
    target_link_libraries(eta_menu_narrator_smoke_test PRIVATE eta_accessibility)

    add_executable(eta_hud_narrator_smoke_test tests/hud_narrator_smoke_test.c)
    target_link_libraries(eta_hud_narrator_smoke_test PRIVATE eta_accessibility)

    add_executable(eta_audio_cue_smoke_test tests/audio_cue_smoke_test.c)
    target_link_libraries(eta_audio_cue_smoke_test PRIVATE eta_accessibility)

    add_executable(eta_navigation_smoke_test tests/navigation_smoke_test.c)
    target_link_libraries(eta_navigation_smoke_test PRIVATE eta_accessibility)

    add_executable(eta_map_survey_smoke_test tests/map_survey_smoke_test.c)
    target_link_libraries(eta_map_survey_smoke_test PRIVATE eta_accessibility)

    add_executable(eta_bsp_ladders_smoke_test tests/bsp_ladders_smoke_test.c)
    target_link_libraries(eta_bsp_ladders_smoke_test PRIVATE eta_accessibility)

    add_executable(eta_bsp_props_smoke_test tests/bsp_props_smoke_test.c)
    target_link_libraries(eta_bsp_props_smoke_test PRIVATE eta_accessibility)

    add_executable(eta_place_classifier_smoke_test tests/place_classifier_smoke_test.c)
    target_link_libraries(eta_place_classifier_smoke_test PRIVATE eta_accessibility)
    add_executable(eta_sniper_spots_smoke_test tests/sniper_spots_smoke_test.c)
    target_link_libraries(eta_sniper_spots_smoke_test PRIVATE eta_accessibility)
    add_executable(eta_rooms_smoke_test tests/rooms_smoke_test.c)
    target_link_libraries(eta_rooms_smoke_test PRIVATE eta_accessibility)

    add_executable(eta_update_check_smoke_test tests/update_check_smoke_test.c)
    target_link_libraries(eta_update_check_smoke_test PRIVATE eta_accessibility)

    # Only means anything on Windows and the Mac, where CI runs it
    # against GitHub.
    if(WIN32 OR APPLE)
        add_executable(eta_windows_update_live_test tests/windows_update_live_test.c)
        target_link_libraries(eta_windows_update_live_test PRIVATE eta_accessibility)
    endif()
endif()
