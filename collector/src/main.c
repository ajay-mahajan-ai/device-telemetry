#include "nbapi_client.h"
#include "reporter.h"

#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>

#define DEFAULT_POLL_INTERVAL_SEC 10

static volatile int running = 1;

static void handle_signal(int sig)
{
    (void)sig;
    running = 0;
}

int main(int argc, char *argv[])
{
    nbapi_client_t client;
    int poll_interval = DEFAULT_POLL_INTERVAL_SEC;

    if (argc > 1) {
        poll_interval = atoi(argv[1]);
        if (poll_interval <= 0) poll_interval = DEFAULT_POLL_INTERVAL_SEC;
    }

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    reporter_log("INFO: telemetry-collector starting (poll every %ds)\n", poll_interval);

    if (nbapi_client_init(&client) != 0) {
        reporter_log("ERROR: Failed to initialize NBAPI client\n");
        return 1;
    }

    while (running) {
        nbapi_client_collect(&client);
        sleep((unsigned int)poll_interval);
    }

    reporter_log("INFO: telemetry-collector stopping\n");
    nbapi_client_cleanup(&client);
    return 0;
}
