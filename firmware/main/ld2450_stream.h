#ifndef LD2450_STREAM_H
#define LD2450_STREAM_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "ld2450_parser.h"

typedef struct {
    uint8_t buffer[LD2450_DATA_FRAME_SIZE];
    size_t length;
} ld2450_stream_t;

void ld2450_stream_init(ld2450_stream_t *stream);

bool ld2450_stream_push_byte(
    ld2450_stream_t *stream,
    uint8_t byte,
    uint8_t output[LD2450_DATA_FRAME_SIZE]
);

#endif /* LD2450_STREAM_H */
