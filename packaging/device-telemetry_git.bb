SUMMARY = "Device telemetry container for RDK-B / prplOS"
DESCRIPTION = "C collector + Python publisher for per-radio WiFi stats via MQTT"
LICENSE = "BSD-2-Clause"
LIC_FILES_CHKSUM = "file://LICENSE;md5=9dfc9fcba82280cc1af1c61a24287420"

SRC_URI = "git://git@github.com/ajay-mahajan-ai/device-telemetry.git;protocol=ssh;branch=main"
PV = "1.0"
SRCREV = "0000000000000000000000000000000000000000"

S = "${WORKDIR}/git"

# Set PLATFORM to "rdkb" or "prplos" before building for a different target
PLATFORM ?= "prplos"
EXTRA_OECMAKE = "-DPLATFORM=${PLATFORM}"

inherit cmake pkgconfig python3native

DEPENDS += " \
    libamxb \
    libamxc \
    libamxd \
    libamxp \
"

RDEPENDS:${PN} += " \
    python3 \
    python3-paho-mqtt \
"

do_install:append() {
    install -d ${D}/usr/bin
    install -m 0755 ${S}/packaging/start.sh ${D}/usr/bin/device-telemetry-start.sh
    # LXC requires /dev and /dev/pts to exist in the rootfs for devpts setup
    install -d ${D}/dev
    install -d ${D}/dev/pts
}

OCI_IMAGE_ENTRYPOINT = "/usr/bin/device-telemetry-start.sh"
OCI_IMAGE_ENTRYPOINT_MAX_TIMEOUT = "30"
