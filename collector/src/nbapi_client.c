#include "nbapi_client.h"
#include "reporter.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

/* Recursively dump amxc_var_t as JSON into a FILE */
static void var_to_json(FILE *f, const amxc_var_t *var, int depth);

static void write_json_string(FILE *f, const char *s)
{
    fputc('"', f);
    for (; *s; s++) {
        unsigned char c = (unsigned char)*s;
        switch (c) {
        case '"':  fputs("\\\"", f); break;
        case '\\': fputs("\\\\", f); break;
        case '\b': fputs("\\b",  f); break;
        case '\f': fputs("\\f",  f); break;
        case '\n': fputs("\\n",  f); break;
        case '\r': fputs("\\r",  f); break;
        case '\t': fputs("\\t",  f); break;
        default:
            if (c < 0x20)
                fprintf(f, "\\u%04x", c);
            else
                fputc(c, f);
        }
    }
    fputc('"', f);
}

static void htable_to_json(FILE *f, const amxc_var_t *var, int depth)
{
    const amxc_htable_t *htable = amxc_var_constcast(amxc_htable_t, var);
    amxc_htable_it_t *it = NULL;
    int first = 1;

    fprintf(f, "{");
    amxc_htable_iterate(it, htable) {
        const char *key = amxc_htable_it_get_key(it);
        amxc_var_t *child = amxc_var_from_htable_it(it);
        if (!first) fprintf(f, ",");
        write_json_string(f, key);
        fputc(':', f);
        var_to_json(f, child, depth + 1);
        first = 0;
    }
    fprintf(f, "}");
}

static void list_to_json(FILE *f, const amxc_var_t *var, int depth)
{
    const amxc_llist_t *list = amxc_var_constcast(amxc_llist_t, var);
    amxc_llist_it_t *it = NULL;
    int first = 1;

    fprintf(f, "[");
    amxc_llist_iterate(it, list) {
        amxc_var_t *child = amxc_var_from_llist_it(it);
        if (!first) fprintf(f, ",");
        var_to_json(f, child, depth + 1);
        first = 0;
    }
    fprintf(f, "]");
}

static void var_to_json(FILE *f, const amxc_var_t *var, int depth)
{
    if (!var) {
        fprintf(f, "null");
        return;
    }

    switch (amxc_var_type_of(var)) {
    case AMXC_VAR_ID_HTABLE:
        htable_to_json(f, var, depth);
        break;
    case AMXC_VAR_ID_LIST:
        list_to_json(f, var, depth);
        break;
    case AMXC_VAR_ID_CSTRING:
    case AMXC_VAR_ID_SSV_STRING:
    case AMXC_VAR_ID_CSV_STRING: {
        const char *s = amxc_var_constcast(cstring_t, var);
        write_json_string(f, s ? s : "");
        break;
    }
    case AMXC_VAR_ID_BOOL:
        fprintf(f, "%s", amxc_var_constcast(bool, var) ? "true" : "false");
        break;
    case AMXC_VAR_ID_INT8:
    case AMXC_VAR_ID_INT16:
    case AMXC_VAR_ID_INT32:
    case AMXC_VAR_ID_INT64:
        fprintf(f, "%lld", (long long)amxc_var_dyncast(int64_t, var));
        break;
    case AMXC_VAR_ID_UINT8:
    case AMXC_VAR_ID_UINT16:
    case AMXC_VAR_ID_UINT32:
    case AMXC_VAR_ID_UINT64:
        fprintf(f, "%llu", (unsigned long long)amxc_var_dyncast(uint64_t, var));
        break;
    default:
        fprintf(f, "null");
        break;
    }
}

int nbapi_client_init(nbapi_client_t *client)
{
    int ret;

    memset(client, 0, sizeof(*client));

    ret = amxb_be_load(AMXB_BACKEND_PATH);
    if (ret != 0) {
        reporter_log("ERROR: Failed to load Ambiorix backend: %s (ret=%d)\n",
                     AMXB_BACKEND_PATH, ret);
        return -1;
    }

    ret = amxb_connect(&client->bus_ctx, AMXB_SOCKET_URI);
    if (ret != 0) {
        reporter_log("ERROR: Failed to connect to %s (ret=%d)\n",
                     AMXB_SOCKET_URI, ret);
        amxb_be_remove_all();
        return -1;
    }

    reporter_log("INFO: Connected to %s\n", AMXB_SOCKET_URI);
    return 0;
}

static void fetch_model_name(nbapi_client_t *client, char *buf, size_t bufsz)
{
    amxc_var_t result;
    amxc_var_t *data;
    amxc_htable_it_t *it;
    const char *mn;
    int ret;

    buf[0] = '\0';
    amxc_var_init(&result);

    ret = amxb_get(client->bus_ctx, DEVICE_INFO_QUERY, 1, &result, 5);
    if (ret != AMXB_STATUS_OK) {
        reporter_log("WARN: amxb_get(%s) failed (ret=%d)\n", DEVICE_INFO_QUERY, ret);
        goto done;
    }

    data = GET_ARG(&result, "0");
    if (!data || amxc_var_type_of(data) != AMXC_VAR_ID_HTABLE) {
        reporter_log("WARN: DeviceInfo result has unexpected type\n");
        goto done;
    }

    /* result is { "Device.DeviceInfo.": { "ModelName": "...", ... } } */
    it = amxc_htable_get_first(amxc_var_constcast(amxc_htable_t, data));
    if (!it) {
        reporter_log("WARN: DeviceInfo htable is empty\n");
        goto done;
    }

    mn = GET_CHAR(amxc_var_from_htable_it(it), "ModelName");
    if (mn && *mn) {
        strncpy(buf, mn, bufsz - 1);
    } else {
        reporter_log("WARN: ModelName not found in DeviceInfo response\n");
    }

done:
    amxc_var_clean(&result);
}

int nbapi_client_collect(nbapi_client_t *client)
{
    amxc_var_t result;
    amxc_var_t *radio_data;
    char tmp_path[sizeof(METRICS_OUTPUT) + 4];
    char model_name[128];
    FILE *f;
    time_t ts;
    int ret;

    amxc_var_init(&result);

    ret = amxb_get(client->bus_ctx, WIFI_RADIO_QUERY, 2, &result, 5);
    if (ret != AMXB_STATUS_OK) {
        reporter_log("WARN: amxb_get(%s) failed (ret=%d)\n", WIFI_RADIO_QUERY, ret);
        amxc_var_clean(&result);
        return -1;
    }

    radio_data = GET_ARG(&result, "0");

    fetch_model_name(client, model_name, sizeof(model_name));

    snprintf(tmp_path, sizeof(tmp_path), "%s.tmp", METRICS_OUTPUT);
    f = fopen(tmp_path, "w");
    if (!f) {
        reporter_log("ERROR: Cannot open %s for writing\n", tmp_path);
        amxc_var_clean(&result);
        return -1;
    }

    time(&ts);
    fprintf(f, "{\"timestamp\":%ld", (long)ts);
    fprintf(f, ",\"model_name\":");
    write_json_string(f, model_name);
    fprintf(f, ",\"radios\":");
    var_to_json(f, radio_data, 0);
    fprintf(f, "}\n");
    fclose(f);

    if (rename(tmp_path, METRICS_OUTPUT) != 0) {
        reporter_log("ERROR: rename %s failed\n", tmp_path);
        amxc_var_clean(&result);
        return -1;
    }

    amxc_var_clean(&result);
    reporter_log("INFO: Telemetry written to %s (model=%s)\n", METRICS_OUTPUT, model_name);
    return 0;
}

void nbapi_client_cleanup(nbapi_client_t *client)
{
    if (client->bus_ctx) {
        amxb_free(&client->bus_ctx);
    }
    amxb_be_remove_all();
}
