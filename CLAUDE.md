# device-telemetry

LCM/LXC container that collects per-radio WiFi stats from an RDK-B device and publishes them to a remote MQTT broker (EMQX on the USP controller).

## Architecture
- **C collector** (`collector/`) — queries `Device.WiFi.Radio.**` via `libamxb`, writes `/tmp/device_telemetry.json` every 10s
- **Python publisher** (`inference/telemetry.py`) — reads metrics JSON, publishes per-radio stats to MQTT

## NBAPI Interface
- Socket: `rbus:/tmp/rtrouted` (RDK-B uses RBus, not ubus — socket at `/tmp/rtrouted` on device)
- Backend: `/usr/bin/mods/amxb/mod-amxb-rbus.so` (mounted from host `/usr/bin/mods/amxb/mod-amxb-rbus.so`)
- Query path: `Device.WiFi.Radio.**`
- Key headers: `<amxb/amxb.h>`, `<amxc/amxc.h>`
- Note: `ubus list` is empty on RDK-B — all DM objects are on RBus via `rtrouted` daemon

## Platform Differences (RDK-B vs prplOS)

The container targets two device types. The bus backend differs between them.

| | RDK-B (x86-64) | prplOS (cortexa53 / ARM) |
|---|---|---|
| Device arch | x86-64 | cortexa53 |
| LCM SDK image | `lcm_sdk_x86-64:v3.2-alpha` | `lcm_sdk_cortexa53:v3.2-alpha` |
| SDK container | `lcm_sdk_rdkb` | `lcm_sdk_prplos` |
| Bus | RBus | ubus |
| Backend `.so` | `mod-amxb-rbus.so` | `mod-amxb-ubus.so` |
| Socket | `/tmp/rtrouted` | `/var/run/ubus/ubus.sock` |
| `AMXB_SOCKET_URI` | `rbus:/tmp/rtrouted` | `ubus:/var/run/ubus.sock` |
| `ubus list` | empty | WiFi objects present |
| WiFi DM path | `Device.WiFi.Radio.**` | `Device.WiFi.Radio.**` |
| Image tag | `:v1.0.0-rdkb` | `:v1.0.0-prplos` |

The platform is selected at build time via `PLATFORM` in `packaging/device-telemetry_git.bb`. No header edits needed — see Build section below.

## MQTT Topics
```
telemetry/<device_id>/radio/<radio_index>
```
- `device_id` = hostname of the device
- `radio_index` = 1, 2, 3 (TR-181 instance index)
- Broker = USP controller's EMQX (port 1883)

## Config
Edit `/etc/device_telemetry.conf` on the device (mounted via HostObject):
```
MQTT_BROKER=<usp_controller_ip>
MQTT_PORT=1883
POLL_INTERVAL_SEC=10
```

## Deploy on device

### RDK-B
```bash
# 1. Create config
echo "MQTT_BROKER=10.10.10.172" > /etc/device_telemetry.conf
echo "MQTT_PORT=1883" >> /etc/device_telemetry.conf

# 2. Install container
ubus-cli 'SoftwareModules.InstallDU(
  URL = "docker://ghcr.io/ajay-mahajan-ai/device-telemetry:v1.0.0-rdkb",
  UUID = "<RFC4122-v5-UUID>",
  ExecutionEnvRef = "generic",
  HostObject = [
    {
      Source = "/tmp/rtrouted",
      Destination = "/tmp/rtrouted",
      Options = "type=mount,bind,rw,create=file"
    },
    {
      Source = "/usr/bin/mods/amxb/mod-amxb-rbus.so",
      Destination = "/usr/bin/mods/amxb/mod-amxb-rbus.so",
      Options = "type=mount,bind,ro,create=file"
    },
    {
      Source = "/etc/device_telemetry.conf",
      Destination = "/etc/device_telemetry.conf",
      Options = "type=mount,bind,ro,create=file"
    }
  ],
  NetworkConfig = { ShareParentNetwork = 1 }
)'
```

### prplOS
```bash
# 1. Create config
echo "MQTT_BROKER=10.10.10.172" > /etc/device_telemetry.conf
echo "MQTT_PORT=1883" >> /etc/device_telemetry.conf

# 2. Install container
ubus-cli 'SoftwareModules.InstallDU(
  URL = "docker://ghcr.io/ajay-mahajan-ai/device-telemetry:v1.0.0-prplos",
  UUID = "<RFC4122-v5-UUID>",
  ExecutionEnvRef = "generic",
  HostObject = [
    {
      Source = "/var/run/ubus/ubus.sock",
      Destination = "/var/run/ubus.sock",
      Options = "type=mount,bind,rw,create=file"
    },
    {
      Source = "/etc/device_telemetry.conf",
      Destination = "/etc/device_telemetry.conf",
      Options = "type=mount,bind,ro,create=file"
    }
  ],
  NetworkConfig = { ShareParentNetwork = 1 }
)'
```
Note: prplOS has `mod-amxb-ubus.so` baked into the image — no need to mount it.

## Build

### Step 1 — Pull SDK images (one-time, on Mac)
```bash
docker login registry.gitlab.com
docker pull registry.gitlab.com/prpl-foundation/lcm/sdk/lcm/lcm_sdk_cortexa53:v3.2-alpha
docker pull registry.gitlab.com/prpl-foundation/lcm/sdk/lcm/lcm_sdk_x86-64:v3.2-alpha
```

### Step 2 — Start SDK containers (one-time, on Mac)
```bash
# prplOS SDK
docker run -it --name lcm_sdk_prplos \
  --platform linux/amd64 \
  -e TZ=Europe/Brussels \
  -v /Users/ajaymahajan/PRPL/device-telemetry:/sdkworkdir/workspace/sources/device-telemetry \
  registry.gitlab.com/prpl-foundation/lcm/sdk/lcm/lcm_sdk_cortexa53:v3.2-alpha

# RDK-B SDK
docker run -it --name lcm_sdk_rdkb \
  --platform linux/amd64 \
  -e TZ=Europe/Brussels \
  -v /Users/ajaymahajan/PRPL/device-telemetry:/sdkworkdir/workspace/sources/device-telemetry \
  registry.gitlab.com/prpl-foundation/lcm/sdk/lcm/lcm_sdk_x86-64:v3.2-alpha

# On subsequent sessions — just attach:
docker start lcm_sdk_prplos && docker exec -it lcm_sdk_prplos /bin/bash
docker start lcm_sdk_rdkb  && docker exec -it lcm_sdk_rdkb  /bin/bash
```

### Step 3 — prplOS build
```bash
# On Mac: set PLATFORM ?= "prplos" in packaging/device-telemetry_git.bb

# Inside lcm_sdk_prplos:
devtool add device-telemetry /sdkworkdir/workspace/sources/device-telemetry
cp /sdkworkdir/workspace/sources/device-telemetry/packaging/device-telemetry_git.bb \
   /sdkworkdir/workspace/recipes/device-telemetry/device-telemetry.bb
devtool build device-telemetry
devtool build-image image-lcm-container-minimal

# Push (inside container):
skopeo copy \
  oci:tmp/deploy/images/container-cortexa53/image-lcm-container-minimal-container-cortexa53-<timestamp>.rootfs-oci \
  docker://ghcr.io/ajay-mahajan-ai/device-telemetry-prplos:v1.0.0 \
  --dest-creds ajay-mahajan-ai:<PAT>
```

### Step 4 — RDK-B build
```bash
# On Mac: set PLATFORM ?= "rdkb" in packaging/device-telemetry_git.bb (default)

# Inside lcm_sdk_rdkb:
devtool add device-telemetry /sdkworkdir/workspace/sources/device-telemetry
cp /sdkworkdir/workspace/sources/device-telemetry/packaging/device-telemetry_git.bb \
   /sdkworkdir/workspace/recipes/device-telemetry/device-telemetry.bb
devtool build device-telemetry
devtool build-image image-lcm-container-minimal

# Push (inside container):
skopeo copy \
  oci:tmp/deploy/images/container-x86-64/image-lcm-container-minimal-container-x86-64-<timestamp>.rootfs-oci \
  docker://ghcr.io/ajay-mahajan-ai/device-telemetry-rdkb:v1.0.0 \
  --dest-creds ajay-mahajan-ai:<PAT>
```
Note: confirm the exact OCI output path after build completes — it includes a timestamp.

## Monitor (on USP controller)
```bash
mosquitto_sub -h localhost -p 1883 -t "telemetry/#" -v
```

## Reference
- LCM SDK cheatsheet: `/Users/ajaymahajan/PRPL/wifi-anomaly-detector/LCM-SDK-CHEATSHEET.md`
- USP Controller: `/Users/ajaymahajan/USP_CONTROLLER/standalone-usp-controller`
- EMQX WebSocket: ws://localhost:8083/mqtt (for browser UI)
