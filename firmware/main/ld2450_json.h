#ifndef LD2450_JSON_H
#define LD2450_JSON_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "ld2450_parser.h"

bool ld2450_format_ground_truth_json(
    const char *node_id,
    uint64_t ts_us,
    uint32_t frame_seq,
    const ld2450_frame_t *frame,
    char *payload,
    size_t payload_capacity,
    size_t *payload_length
);

#endif /* LD2450_JSON_H */
