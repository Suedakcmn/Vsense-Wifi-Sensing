#include "ld2450_json.h"

#include <math.h>
#include <stdarg.h>
#include <stdio.h>

static bool ld2450_append_json(
    char *payload,
    size_t payload_capacity,
    size_t *payload_length,
    const char *format,
    ...
)
{
    if (*payload_length >= payload_capacity) {
        return false;
    }

    va_list arguments;
    va_start(arguments, format);
    int written = vsnprintf(
        &payload[*payload_length],
        payload_capacity - *payload_length,
        format,
        arguments
    );
    va_end(arguments);

    if (
        written < 0 ||
        (size_t)written >= payload_capacity - *payload_length
    ) {
        return false;
    }

    *payload_length += (size_t)written;
    return true;
}

bool ld2450_format_ground_truth_json(
    const char *node_id,
    uint64_t ts_us,
    uint32_t frame_seq,
    const ld2450_frame_t *frame,
    char *payload,
    size_t payload_capacity,
    size_t *payload_length
)
{
    if (
        node_id == NULL ||
        frame == NULL ||
        payload == NULL ||
        payload_capacity == 0 ||
        payload_length == NULL
    ) {
        return false;
    }

    *payload_length = 0;

    if (!ld2450_append_json(
            payload,
            payload_capacity,
            payload_length,
            "{\"schema_version\":1,"
            "\"message_type\":\"ground_truth\","
            "\"node_id\":\"%s\","
            "\"ts_us\":%llu,"
            "\"frame_seq\":%lu,"
            "\"targets\":[",
            node_id,
            (unsigned long long)ts_us,
            (unsigned long)frame_seq
        )) {
        return false;
    }

    bool first_target = true;
    for (size_t index = 0; index < LD2450_MAX_TARGETS; index++) {
        const ld2450_target_t *target = &frame->targets[index];
        if (!target->present) {
            continue;
        }

        int64_t x = target->x_mm;
        int64_t y = target->y_mm;
        uint32_t distance_mm = (uint32_t)lround(
            sqrt((double)((x * x) + (y * y)))
        );

        if (!ld2450_append_json(
                payload,
                payload_capacity,
                payload_length,
                "%s{\"target_id\":%u,"
                "\"x_mm\":%d,"
                "\"y_mm\":%d,"
                "\"speed_cm_s\":%d,"
                "\"distance_mm\":%lu,"
                "\"resolution_mm\":%u}",
                first_target ? "" : ",",
                (unsigned int)target->target_id,
                (int)target->x_mm,
                (int)target->y_mm,
                (int)target->speed_cm_s,
                (unsigned long)distance_mm,
                (unsigned int)target->resolution_mm
            )) {
            return false;
        }

        first_target = false;
    }

    return ld2450_append_json(
        payload,
        payload_capacity,
        payload_length,
        "]}"
    );
}
