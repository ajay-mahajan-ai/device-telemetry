set(PLATFORM "rdkb" CACHE STRING "Target platform: rdkb or prplos")
set_property(CACHE PLATFORM PROPERTY STRINGS rdkb prplos)

if(PLATFORM STREQUAL "rdkb")
    set(AMXB_BACKEND_PATH  "/usr/bin/mods/amxb/mod-amxb-rbus.so")
    set(AMXB_SOCKET_URI    "rbus:/tmp/rtrouted")
    set(WIFI_RADIO_QUERY   "Device.WiFi.Radio.")
    set(DEVICE_INFO_QUERY  "Device.DeviceInfo.")
elseif(PLATFORM STREQUAL "prplos")
    set(AMXB_BACKEND_PATH  "/usr/bin/mods/amxb/mod-amxb-ubus.so")
    set(AMXB_SOCKET_URI    "ubus:/var/run/ubus.sock")
    set(WIFI_RADIO_QUERY   "WiFi.Radio.")
    set(DEVICE_INFO_QUERY  "DeviceInfo.")
else()
    message(FATAL_ERROR "Unknown PLATFORM '${PLATFORM}'. Use -DPLATFORM=rdkb or -DPLATFORM=prplos")
endif()

message(STATUS "Platform: ${PLATFORM}  backend: ${AMXB_BACKEND_PATH}  socket: ${AMXB_SOCKET_URI}  query: ${WIFI_RADIO_QUERY}")

find_package(PkgConfig)

if(PKG_CONFIG_FOUND)
    pkg_check_modules(AMXB libamxb)
    pkg_check_modules(AMXC libamxc)
    pkg_check_modules(AMXD libamxd)
    pkg_check_modules(AMXP libamxp)
endif()

add_executable(telemetry-collector
    src/main.c
    src/nbapi_client.c
    src/reporter.c
)

target_compile_definitions(telemetry-collector PRIVATE
    AMXB_BACKEND_PATH="${AMXB_BACKEND_PATH}"
    AMXB_SOCKET_URI="${AMXB_SOCKET_URI}"
    WIFI_RADIO_QUERY="${WIFI_RADIO_QUERY}"
    DEVICE_INFO_QUERY="${DEVICE_INFO_QUERY}"
)

target_include_directories(telemetry-collector PRIVATE
    include
    ${AMXB_INCLUDE_DIRS}
    ${AMXC_INCLUDE_DIRS}
    ${AMXD_INCLUDE_DIRS}
    ${AMXP_INCLUDE_DIRS}
)

if(AMXB_FOUND)
    target_link_libraries(telemetry-collector
        ${AMXB_LIBRARIES}
        ${AMXC_LIBRARIES}
        ${AMXD_LIBRARIES}
        ${AMXP_LIBRARIES}
    )
else()
    target_link_libraries(telemetry-collector amxb amxc amxd amxp)
endif()

install(TARGETS telemetry-collector DESTINATION /usr/bin)
