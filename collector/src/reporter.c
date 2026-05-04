#include "reporter.h"

#include <stdio.h>
#include <stdarg.h>
#include <syslog.h>

void reporter_log(const char *fmt, ...)
{
    va_list args;
    va_start(args, fmt);
    vfprintf(stderr, fmt, args);
    va_end(args);

    va_start(args, fmt);
    vsyslog(LOG_INFO, fmt, args);
    va_end(args);
}
