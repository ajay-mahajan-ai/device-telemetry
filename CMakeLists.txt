cmake_minimum_required(VERSION 3.10)
project(device-telemetry C)

add_subdirectory(collector)

install(FILES inference/telemetry.py
    DESTINATION /usr/share/device-telemetry
    PERMISSIONS OWNER_READ OWNER_EXECUTE GROUP_READ GROUP_EXECUTE WORLD_READ WORLD_EXECUTE
)

install(FILES config/device_telemetry.conf
    DESTINATION /usr/share/device-telemetry
)
