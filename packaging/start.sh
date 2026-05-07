#!/bin/sh
# PID 1 supervisor for device-telemetry container

COLLECTOR=/usr/bin/telemetry-collector
PUBLISHER=/usr/share/device-telemetry/telemetry.py
HOST_CONFIG=/etc/device_telemetry.conf
IMAGE_CONFIG=/usr/share/device-telemetry/device_telemetry.conf

# Load host-mounted config first (overrides image defaults)
if [ -f "$HOST_CONFIG" ]; then
    . "$HOST_CONFIG"
elif [ -f "$IMAGE_CONFIG" ]; then
    . "$IMAGE_CONFIG"
fi

POLL_INTERVAL_SEC=${POLL_INTERVAL_SEC:-10}
MQTT_BROKER=${MQTT_BROKER:-localhost}
MQTT_PORT=${MQTT_PORT:-1883}

log() { echo "[device-telemetry] $*"; }

start_collector() {
    log "Starting telemetry-collector (poll=${POLL_INTERVAL_SEC}s)"
    $COLLECTOR "$POLL_INTERVAL_SEC" &
    COLLECTOR_PID=$!
}

start_publisher() {
    log "Starting telemetry.py (broker=${MQTT_BROKER}:${MQTT_PORT})"
    python3 "$PUBLISHER" \
        --broker "$MQTT_BROKER" \
        --port   "$MQTT_PORT" \
        --interval $(( POLL_INTERVAL_SEC + 1 )) &
    PUBLISHER_PID=$!
}

cleanup() {
    log "SIGTERM received — shutting down"
    kill "$COLLECTOR_PID" "$PUBLISHER_PID" 2>/dev/null
    wait
    exit 0
}

trap cleanup TERM INT

start_collector
start_publisher

while true; do
    sleep 5

    if ! kill -0 "$COLLECTOR_PID" 2>/dev/null; then
        log "WARN: telemetry-collector exited — restarting"
        start_collector
    fi

    if ! kill -0 "$PUBLISHER_PID" 2>/dev/null; then
        log "WARN: telemetry.py exited — restarting"
        start_publisher
    fi
done
