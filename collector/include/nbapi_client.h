#ifndef NBAPI_CLIENT_H
#define NBAPI_CLIENT_H

#include <amxc/amxc.h>
#include <amxp/amxp.h>
#include <amxd/amxd_types.h>
#include <amxb/amxb.h>

/* AMXB_BACKEND_PATH, AMXB_SOCKET_URI, WIFI_RADIO_QUERY set by CMake via -DPLATFORM=rdkb|prplos */
#ifndef AMXB_BACKEND_PATH
#error "AMXB_BACKEND_PATH not defined — build with -DPLATFORM=rdkb or -DPLATFORM=prplos"
#endif
#ifndef AMXB_SOCKET_URI
#error "AMXB_SOCKET_URI not defined — build with -DPLATFORM=rdkb or -DPLATFORM=prplos"
#endif
#ifndef WIFI_RADIO_QUERY
#error "WIFI_RADIO_QUERY not defined — build with -DPLATFORM=rdkb or -DPLATFORM=prplos"
#endif
#ifndef DEVICE_INFO_QUERY
#error "DEVICE_INFO_QUERY not defined — build with -DPLATFORM=rdkb or -DPLATFORM=prplos"
#endif

#define METRICS_OUTPUT     "/tmp/device_telemetry.json"

typedef struct {
    amxb_bus_ctx_t *bus_ctx;
} nbapi_client_t;

int nbapi_client_init(nbapi_client_t *client);
int nbapi_client_collect(nbapi_client_t *client);
void nbapi_client_cleanup(nbapi_client_t *client);

#endif /* NBAPI_CLIENT_H */
