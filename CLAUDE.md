# device-telemetry

LCM/LXC container that collects per-radio WiFi stats from an RDK-B or prplOS device and publishes them to a remote MQTT broker (EMQX on the USP controller).

## Architecture
- **C collector** (`collector/`) — queries WiFi Radio DM objects via `libamxb`, writes `/tmp/device_telemetry.json` every 10s
- **Python publisher** (`inference/telemetry.py`) — reads metrics JSON, publishes per-radio stats to MQTT
- WiFi DM query path is platform-specific: `Device.WiFi.Radio.**` (RDK-B) or `WiFi.Radio.**` (prplOS) — set at build time via `PLATFORM`

## NBAPI Interface
- Socket: `rbus:/tmp/rtrouted` (RDK-B uses RBus, not ubus — socket at `/tmp/rtrouted` on device)
- Backend: `/usr/bin/mods/amxb/mod-amxb-rbus.so` (mounted from host `/usr/bin/mods/amxb/mod-amxb-rbus.so`)
- Query path: `Device.WiFi.Radio.**`
- Key headers: `<amxb/amxb.h>`, `<amxc/amxc.h>`
- Note: `ubus list` is empty on RDK-B — all DM objects are on RBus via `rtrouted` daemon

## Platform Differences (RDK-B vs prplOS)

The container targets two device types. The bus backend differs between them.

| | RDK-B (aarch64) | prplOS (cortexa53 / ARM) |
|---|---|---|
| Device arch | cortexa53 (aarch64) | cortexa53 (aarch64) |
| LCM SDK image | `lcm_sdk_cortexa53:v3.2-alpha` | `lcm_sdk_cortexa53:v3.2-alpha` |
| SDK container | `lcm_sdk_prplos` (same SDK, different PLATFORM) | `lcm_sdk_prplos` |
| Build flag | `PLATFORM = "rdkb"` in local.conf | `PLATFORM = "prplos"` (default) |
| Bus | RBus | ubus |
| Backend `.so` | `mod-amxb-rbus.so` (mounted from host) | `mod-amxb-ubus.so` (baked in) |
| Socket | `/tmp/rtrouted` | `/var/run/ubus/ubus.sock` |
| `AMXB_SOCKET_URI` | `rbus:/tmp/rtrouted` | `ubus:/var/run/ubus.sock` |
| `ubus list` | empty | WiFi objects present |
| WiFi DM path | `Device.WiFi.Radio.**` | `WiFi.Radio.**` |
| Image tag | `:v1.0.0-rdkb` | `:v1.0.0-prplos` |

Both platforms use the **same cortexa53 SDK**. Only the `PLATFORM` build flag differs.
The `lcm_sdk_rdkb` container (x86-64 SDK) is **not used** — the device is aarch64.

The platform is selected at build time by setting `PLATFORM = "rdkb"` in `conf/local.conf`
before running `devtool build`. No header edits needed — see Build section below.

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

# 2. Install container (use the latest pushed image tag)
ubus-cli 'SoftwareModules.InstallDU(
  URL = "docker://ghcr.io/ajay-mahajan-ai/device-telemetry-rdkb:<tag>",
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

# 2. Install container (use the latest pushed image tag)
ubus-cli 'SoftwareModules.InstallDU(
  URL = "docker://ghcr.io/ajay-mahajan-ai/device-telemetry-prplos:<tag>",
  UUID = "<RFC4122-v5-UUID>",
  ExecutionEnvRef = "generic",
  AutoStart = true,
  Privileged = true,
  HostObject = [
    {
      Source = "/var/run/ubus/ubus.sock",
      Destination = "/run/ubus.sock",
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

### Step 1 — Pull SDK images (one-time)
```bash
docker login registry.gitlab.com
docker pull registry.gitlab.com/prpl-foundation/lcm/sdk/lcm/lcm_sdk_cortexa53:v3.2-alpha
docker pull registry.gitlab.com/prpl-foundation/lcm/sdk/lcm/lcm_sdk_x86-64:v3.2-alpha
```

### Step 2 — Start SDK containers (one-time)

**On Mac** (bind-mount from host path):
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
```

**On Ubuntu** — use a local copy inside the container instead of bind-mounting (see Build Environment Gotchas below):
```bash
# prplOS SDK
docker run -it --name lcm_sdk_prplos \
  --platform linux/amd64 \
  -e TZ=Europe/Brussels \
  -v /home/ajay/containers/device-telemetry:/sdkworkdir/workspace/sources/device-telemetry \
  registry.gitlab.com/prpl-foundation/lcm/sdk/lcm/lcm_sdk_cortexa53:v3.2-alpha

# RDK-B SDK
docker run -it --name lcm_sdk_rdkb \
  --platform linux/amd64 \
  -e TZ=Europe/Brussels \
  -v /home/ajay/containers/device-telemetry:/sdkworkdir/workspace/sources/device-telemetry \
  registry.gitlab.com/prpl-foundation/lcm/sdk/lcm/lcm_sdk_x86-64:v3.2-alpha
```

On subsequent sessions — just attach, then run Step 3:
```bash
docker start lcm_sdk_prplos && docker exec -it lcm_sdk_prplos /bin/bash
docker start lcm_sdk_rdkb  && docker exec -it lcm_sdk_rdkb  /bin/bash
```

### Step 3 — Source the build environment (every session, inside container)

Run at the start of every `docker exec` session before building:

```bash
source /sdkworkdir/environment-setup-cortexa53-oe-linux                # cross-compiler + devtool
source /sdkworkdir/buildtools/environment-setup-x86_64-oesdk-linux     # build toolchain
export PATH=/sdkworkdir/layers/poky/bitbake/bin:$PATH                  # bitbake
```

- `environment-setup-cortexa53-oe-linux` enables `devtool`
- `environment-setup-x86_64-oesdk-linux` sets up the build toolchain but does **not** add `bitbake` to PATH
- `bitbake` lives at `layers/poky/bitbake/bin/` and must be added to PATH explicitly

These three lines are appended to `~/.bashrc` inside the container so they load automatically. To set up on a fresh container:
```bash
echo 'source /sdkworkdir/environment-setup-cortexa53-oe-linux' >> ~/.bashrc
echo 'source /sdkworkdir/buildtools/environment-setup-x86_64-oesdk-linux' >> ~/.bashrc
echo 'export PATH=/sdkworkdir/layers/poky/bitbake/bin:$PATH' >> ~/.bashrc
```

### Step 4 — prplOS build (Ubuntu, inside lcm_sdk_prplos)

```bash
# One-time: git identity inside the container
git config --global user.email "lcmuser@build"
git config --global user.name "lcmuser"

# Copy source to a path lcmuser fully owns:
cp -r /sdkworkdir/workspace/sources/device-telemetry /home/lcmuser/device-telemetry
cd /home/lcmuser/device-telemetry
git init && git add -A . && git commit -m "initial"

# Register with devtool:
cd /sdkworkdir
devtool reset -n device-telemetry 2>/dev/null || true
devtool add device-telemetry /home/lcmuser/device-telemetry

# Copy recipe (CRITICAL: _git.bb not device-telemetry.bb — see Gotcha #3):
cp /home/lcmuser/device-telemetry/packaging/device-telemetry_git.bb \
   /sdkworkdir/workspace/recipes/device-telemetry/device-telemetry_git.bb
rm -f /sdkworkdir/workspace/recipes/device-telemetry/device-telemetry.bb

# Set OCI entrypoint in local.conf (CRITICAL: bbappend does not work — see Gotcha #6):
grep -q "OCI_IMAGE_ENTRYPOINT" conf/local.conf || \
  echo 'OCI_IMAGE_ENTRYPOINT = "/usr/bin/device-telemetry-start.sh"' >> conf/local.conf
grep -q "OCI_IMAGE_ENTRYPOINT_MAX_TIMEOUT" conf/local.conf || \
  echo 'OCI_IMAGE_ENTRYPOINT_MAX_TIMEOUT = "30"' >> conf/local.conf

bitbake -c cleansstate device-telemetry
devtool build device-telemetry
devtool build-image image-lcm-container-minimal
```

Push:
```bash
skopeo copy \
  oci:tmp/deploy/images/container-cortexa53/image-lcm-container-minimal-container-cortexa53-<timestamp>.rootfs-oci \
  docker://ghcr.io/ajay-mahajan-ai/device-telemetry-prplos:<tag> \
  --dest-creds ajay-mahajan-ai:<PAT>
```

### Step 5 — RDK-B build (Ubuntu, inside lcm_sdk_rdkb)

Same local-copy pattern as prplOS:

```bash
# One-time: git identity inside the container
git config --global user.email "lcmuser@build"
git config --global user.name "lcmuser"

# Copy source to a path lcmuser fully owns:
cp -r /sdkworkdir/workspace/sources/device-telemetry /home/lcmuser/device-telemetry
cd /home/lcmuser/device-telemetry
git init && git add -A . && git commit -m "initial"

# Register with devtool:
cd /sdkworkdir
devtool reset -n device-telemetry 2>/dev/null || true
devtool add device-telemetry /home/lcmuser/device-telemetry

# Copy recipe:
cp /home/lcmuser/device-telemetry/packaging/device-telemetry_git.bb \
   /sdkworkdir/workspace/recipes/device-telemetry/device-telemetry_git.bb
rm -f /sdkworkdir/workspace/recipes/device-telemetry/device-telemetry.bb

# Set OCI entrypoint in local.conf:
grep -q "OCI_IMAGE_ENTRYPOINT" conf/local.conf || \
  echo 'OCI_IMAGE_ENTRYPOINT = "/usr/bin/device-telemetry-start.sh"' >> conf/local.conf
grep -q "OCI_IMAGE_ENTRYPOINT_MAX_TIMEOUT" conf/local.conf || \
  echo 'OCI_IMAGE_ENTRYPOINT_MAX_TIMEOUT = "30"' >> conf/local.conf

bitbake -c cleansstate device-telemetry
devtool build device-telemetry
devtool build-image image-lcm-container-minimal
```

Push (confirm exact path — it includes a timestamp):
```bash
skopeo copy \
  oci:tmp/deploy/images/container-x86-64/image-lcm-container-minimal-container-x86-64-<timestamp>.rootfs-oci \
  docker://ghcr.io/ajay-mahajan-ai/device-telemetry-rdkb:<tag> \
  --dest-creds ajay-mahajan-ai:<PAT>
```

### Full clean rebuild (Ubuntu — use when build is suspect or entrypoint still wrong)

Wipes the local source copy, deploy artifacts, and sstate before rebuilding from scratch.
Run inside `lcm_sdk_prplos` (source the environment per Step 3 first):

```bash
# 1. Fresh local copy (eliminates ownership/stale-file issues)
rm -rf /home/lcmuser/device-telemetry
cp -r /sdkworkdir/workspace/sources/device-telemetry /home/lcmuser/device-telemetry
cd /home/lcmuser/device-telemetry
git init && git add -A . && git commit -m "clean build"

# 2. Reset devtool and re-register
cd /sdkworkdir
devtool reset -n device-telemetry 2>/dev/null || true
devtool add device-telemetry /home/lcmuser/device-telemetry

# 3. Copy recipe (correct _git.bb name, remove stale .bb)
cp /home/lcmuser/device-telemetry/packaging/device-telemetry_git.bb \
   /sdkworkdir/workspace/recipes/device-telemetry/device-telemetry_git.bb
rm -f /sdkworkdir/workspace/recipes/device-telemetry/device-telemetry.bb

# 4. Set OCI_IMAGE_ENTRYPOINT in local.conf
# (bbappend is NOT used — workspace layer.conf BBFILES only includes *.bb, not *.bbappend)
grep -q "OCI_IMAGE_ENTRYPOINT" conf/local.conf || \
  echo 'OCI_IMAGE_ENTRYPOINT = "/usr/bin/device-telemetry-start.sh"' >> conf/local.conf
grep -q "OCI_IMAGE_ENTRYPOINT_MAX_TIMEOUT" conf/local.conf || \
  echo 'OCI_IMAGE_ENTRYPOINT_MAX_TIMEOUT = "30"' >> conf/local.conf
# Verify — must show /usr/bin/device-telemetry-start.sh before proceeding
bitbake -e image-lcm-container-minimal | grep "^OCI_IMAGE_ENTRYPOINT="

# 5. Wipe old deploy artifacts and sstate
rm -rf tmp/deploy/images/container-cortexa53/image-lcm-container-minimal*
bitbake -c cleansstate device-telemetry
bitbake -c cleansstate image-lcm-container-minimal

# 6. Build
devtool build device-telemetry
devtool build-image image-lcm-container-minimal
```

### Verifying the OCI image entrypoint before pushing

Always confirm the built image has the correct entrypoint before pushing:

```bash
TIMESTAMP=$(ls -d tmp/deploy/images/container-cortexa53/image-lcm-container-minimal-container-cortexa53-[0-9]*.rootfs-oci 2>/dev/null | sort | tail -1)
echo "Using: $TIMESTAMP"

TIMESTAMP=$(ls -d tmp/deploy/images/container-x86-64/image-lcm-container-minimal-container-x86-64-[0-9]*.rootfs-oci 2>/dev/null | sort | tail -1)
echo "Using: $TIMESTAMP"

MANIFEST_HASH=$(python3 -c "
import json
with open('$TIMESTAMP/index.json') as f:
    print(json.load(f)['manifests'][0]['digest'].split(':')[1])
")

CONFIG_HASH=$(python3 -c "
import json
with open('$TIMESTAMP/blobs/sha256/$MANIFEST_HASH') as f:
    print(json.load(f)['config']['digest'].split(':')[1])
")

python3 -m json.tool $TIMESTAMP/blobs/sha256/$CONFIG_HASH | grep -A3 "Entrypoint\|\"Cmd\""
```

Expected output:
```json
"Entrypoint": [
    "/usr/bin/device-telemetry-start.sh"
],
```

If `"Entrypoint": []` or missing — `OCI_IMAGE_ENTRYPOINT` was not set in `conf/local.conf`. Check:
```bash
grep OCI_IMAGE_ENTRYPOINT conf/local.conf
bitbake -e image-lcm-container-minimal | grep "^OCI_IMAGE_ENTRYPOINT="
```
Then re-run Full clean rebuild steps 4–6.

Note: for RDK-B, replace `container-cortexa53` with `container-x86-64` in the `TIMESTAMP` glob above.

### Syncing edits back from the local copy to the bind-mounted source (Ubuntu)

When editing inside the SDK container (`/home/lcmuser/device-telemetry`), changes are NOT automatically reflected in `/home/ajay/containers/device-telemetry` on the Ubuntu host. After a successful build, sync back:

```bash
# Inside SDK container — copy changed files back to the bind-mount:
cp -r /home/lcmuser/device-telemetry/. /sdkworkdir/workspace/sources/device-telemetry/

# Then on Ubuntu host — commit and push from the real source dir:
cd /home/ajay/containers/device-telemetry
git add -A && git commit -m "your message"
git push
```

Or edit on the Ubuntu host first, then re-copy into the local copy before rebuilding:
```bash
# Ubuntu host → SDK container (repeat for any changed files)
cp /home/ajay/containers/device-telemetry/packaging/device-telemetry_git.bb \
   /home/lcmuser/device-telemetry/packaging/device-telemetry_git.bb
```

## Build Environment Gotchas (Ubuntu / LCM SDK)

These issues only manifest on Ubuntu; Mac builds don't hit them because Docker Desktop maps UIDs transparently.

### 1. Bind-mount git ownership error (`fatal: detected dubious ownership`)

The Ubuntu host user (`ajay`, UID 1000) owns `/home/ajay/containers/device-telemetry`. When Docker bind-mounts this into the container, `lcmuser` (a different UID inside the container) sees files it doesn't own. Git 2.34.1 (the version in the SDK container) refuses to run in a directory owned by a different user.

Adding `git config --global --add safe.directory ...` fixes interactive `git` commands but does **not** fix `devtool build`. During a build, `bitbake`'s `externalsrc` class runs `git add -A .` in a subprocess with a stripped environment — the HOME-based gitconfig is not reliably passed through. This subprocess fails with exit code 128.

**The only reliable fix**: copy the source to a path that `lcmuser` fully owns:
```bash
cp -r /sdkworkdir/workspace/sources/device-telemetry /home/lcmuser/device-telemetry
```
Then pass `/home/lcmuser/device-telemetry` to `devtool add`.

### 2. `safe.directory = *` wildcard doesn't work (git 2.34.1)

The `safe.directory = *` glob was added in git 2.35.3. The SDK container ships git 2.34.1, which does not support it. Per-path entries work but don't help for the bitbake subprocess reason above.

### 3. Correct recipe filename: `device-telemetry_git.bb` not `device-telemetry.bb`

`devtool add` creates the recipe file as `<name>_git.bb`. If you `cp` your recipe to `device-telemetry.bb`, bitbake sees two recipes for the same package and picks the wrong auto-generated stub (no `DEPENDS`, no `EXTRA_OECMAKE`, `SRCREV = "0000..."`).

Always copy to the exact name devtool created:
```bash
cp packaging/device-telemetry_git.bb \
   /sdkworkdir/workspace/recipes/device-telemetry/device-telemetry_git.bb
rm -f /sdkworkdir/workspace/recipes/device-telemetry/device-telemetry.bb
```

### 4. One-time git identity setup inside the container

```bash
git config --global user.email "lcmuser@build"
git config --global user.name "lcmuser"
```

### 5. Stale cmake cache after recipe/DEPENDS fix

If you previously built with the wrong recipe, the sysroot is missing `amxc` headers and cmake's cache has wrong defines. Always run:
```bash
bitbake -c cleansstate device-telemetry
```
before rebuilding to avoid `amxc/amxc.h: No such file or directory`.

### 6. `OCI_IMAGE_ENTRYPOINT` must be set in `local.conf`, not in the package recipe

`OCI_IMAGE_ENTRYPOINT = "/usr/bin/device-telemetry-start.sh"` in `device-telemetry_git.bb` has no effect on the built OCI image. Each bitbake recipe has its own variable namespace — the package recipe's variables are invisible to the image recipe. The image recipe (`image-lcm-container-minimal.bb`) has its own `OCI_IMAGE_ENTRYPOINT ?= "/sbin/init"` which wins.

**Symptom:** `lxc.init.cmd = /sbin/init` in the generated LXC config; container exits immediately because `/sbin/init` doesn't exist in the minimal rootfs.

**A `.bbappend` in the devtool workspace does NOT work** — the workspace `layer.conf` only registers `*.bb` files in `BBFILES`, not `*.bbappend`. The bbappend is silently ignored.

**Diagnosis:**
```bash
bitbake -e image-lcm-container-minimal | grep "^OCI_IMAGE_ENTRYPOINT="
# → OCI_IMAGE_ENTRYPOINT="/sbin/init"  (wrong)

cat /sdkworkdir/workspace/conf/layer.conf | grep BBFILES
# → only *.bb, no *.bbappend
```

**Fix:** Set the variable in `conf/local.conf`:
```bash
echo 'OCI_IMAGE_ENTRYPOINT = "/usr/bin/device-telemetry-start.sh"' >> conf/local.conf
echo 'OCI_IMAGE_ENTRYPOINT_MAX_TIMEOUT = "30"' >> conf/local.conf

# Verify
bitbake -e image-lcm-container-minimal | grep "^OCI_IMAGE_ENTRYPOINT="
# → OCI_IMAGE_ENTRYPOINT="/usr/bin/device-telemetry-start.sh"  (correct)
```

This `local.conf` entry must be present every time `devtool build-image image-lcm-container-minimal` is run. The `packaging/image-lcm-container-minimal.bbappend` file in the repo is kept for reference but is not used with the devtool workflow.

### 7. File ownership after partial sync (UID mismatch in local copy)

When files are copied from the bind-mounted source (owned by host UID 1002 / `ajay`) into `/home/lcmuser/device-telemetry/`, they keep their original UID. `lcmuser` cannot overwrite them.

**Symptom:** `cp: cannot create regular file '...': Permission denied` even though `ls -la` shows `lcmuser` owns the parent directory.

**Fix:** Remove the host-owned file (directory owner can always unlink) then re-copy:
```bash
rm /home/lcmuser/device-telemetry/packaging/device-telemetry_git.bb
cp /sdkworkdir/workspace/sources/device-telemetry/packaging/device-telemetry_git.bb \
   /home/lcmuser/device-telemetry/packaging/device-telemetry_git.bb
```
Check all subdirs — `collector/` and `packaging/` are the most commonly affected.

## prplware-v42 Platform Patches

These patches must be applied to the prplware-v42 build before the container works reliably on prplOS. Patches live at `/home/ajay/prplware-v42/my-fixes/` following the same directory tree as `feeds/feed_lcm/`.

| Patch | Package | What it fixes |
|---|---|---|
| `feed_lcm/libs/librlyeh/patches/001-blobs-symlink.patch` | librlyeh | rlyeh creates a `blobs/` symlink in the image dir so the OCI layer can be unpacked by cthulhu |
| `feed_lcm/mods/timingila-cthulhu/patches/001-reconstruct-hostobject-list.patch` | timingila-cthulhu | Parses flat `HostObject.N.Source/Destination/Options` keys from ubus-cli into the structured list cthulhu needs, so socket and config mounts land in the LXC config |
| `feed_lcm/apps/cthulhu/patches/001-overlayfs-start-fallback.patch` | cthulhu | Checks return value of `cthulhu_overlayfs_create_rootfs`; if storage dir is unavailable (null data_dir), retries with `/tmp/cthulhu_scratch` so the container gets a writable overlayfs instead of an empty rootfs |
| `feed_lcm/mods/cthulhu-lxc/patches/001-shareparentnetwork-use-host-netns.patch` | cthulhu-lxc | When `ShareParentNetwork = 1`, writes `lxc.namespace.share.net = 1` (host init) instead of the sandbox namespace process PID; the sandbox clone inherits cthulhu's restricted netns, not the host root netns, so without this fix the container has no network |

To apply, copy each patch file to the corresponding `patches/` subdirectory under the feed package, then rebuild the affected package with `make package/feeds/feed_lcm/<pkg>/compile`.

## Troubleshooting

### Container is STOPPED immediately after install

**Symptom:** `lxc-ls --fancy` shows `STOPPED`; syslog shows `Starting → Running → Stopped` within 1 second; autorestart not triggered.

**Diagnosis flow:**
```bash
# 1. Check the LXC config entrypoint
grep "init.cmd" /etc/config/lxc/<uuid>/config

# 2. Check what's in the rootfs (is usr/ present?)
ls /lcm/cthulhu/rootfs/<uuid>/

# 3. Check the OCI image config for Entrypoint/Cmd fields
cat /lcm/rlyeh/images/<org>/<image>/index.json
# → get manifest digest, then:
cat /lcm/rlyeh/blobs/sha256/<manifest-hash> | python3 -m json.tool | grep -A5 "Entrypoint\|Cmd"
```

**Case A — `lxc.init.cmd = /sbin/init` and no `usr/` in rootfs:**
Root cause: `OCI_IMAGE_ENTRYPOINT` was not set in `conf/local.conf` when the image was built (see Gotcha #6). The image recipe's `?= "/sbin/init"` default was used, and `/sbin/init` doesn't exist in the minimal rootfs. Fix: add `OCI_IMAGE_ENTRYPOINT` to `conf/local.conf`, cleansstate the image, and rebuild.

**Case B — correct `lxc.init.cmd` but rootfs is empty:**
Root cause: stale bitbake sstate — the package was not re-installed into the image. Fix: `bitbake -c cleansstate device-telemetry && bitbake -c cleansstate image-lcm-container-minimal`, then rebuild both.

**Case C — correct `lxc.init.cmd` and rootfs has `usr/bin/` — collector crashes:**
The entrypoint runs but exits. Attach immediately after start:
```bash
lxc-attach -n <uuid> -- /bin/sh
/usr/bin/telemetry-collector 10
```
Common cause: wrong `WIFI_RADIO_QUERY` for the platform. prplOS uses `WiFi.Radio.**`, not `Device.WiFi.Radio.**`. Verify `PLATFORM=prplos` was set at build time.

### Collector logs "amxb_get failed (ret=2)"

WiFi DM path mismatch. prplOS exposes `WiFi.Radio.**` (no `Device.` prefix). The binary was built with the wrong `PLATFORM`. Rebuild with `-DPLATFORM=prplos` (set via `PLATFORM ?= "prplos"` in the recipe).

Verify inside a running container:
```bash
ubus list | grep -i wifi   # should show WiFi.Radio.1 / WiFi.Radio.2 / WiFi.Radio.3
```

## Monitor (on USP controller)
```bash
mosquitto_sub -h localhost -p 1883 -t "telemetry/#" -v
```

## Reference
- LCM SDK cheatsheet: `/Users/ajaymahajan/PRPL/wifi-anomaly-detector/LCM-SDK-CHEATSHEET.md`
- USP Controller: `/Users/ajaymahajan/USP_CONTROLLER/standalone-usp-controller`
- EMQX WebSocket: ws://localhost:8083/mqtt (for browser UI)
