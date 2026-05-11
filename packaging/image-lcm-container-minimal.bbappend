# OCI_IMAGE_ENTRYPOINT set in device-telemetry_git.bb (the package recipe) is in a
# separate bitbake namespace and is NOT visible to image-lcm-container-minimal at
# image build time. The image recipe's own ?= default (/sbin/init) wins.
# This bbappend overrides it with the correct supervisor entrypoint.
OCI_IMAGE_ENTRYPOINT = "/usr/bin/device-telemetry-start.sh"
OCI_IMAGE_ENTRYPOINT_MAX_TIMEOUT = "30"

