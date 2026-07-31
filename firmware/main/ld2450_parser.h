#ifndef LD2450_PARSER_H
#define LD2450_PARSER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define LD2450_MAX_TARGETS 3
#define LD2450_TARGET_BLOCK_SIZE 8
#define LD2450_DATA_FRAME_SIZE 30

typedef struct {
    uint8_t target_id;
    bool present;
    int16_t x_mm;
    int16_t y_mm;
    int16_t speed_cm_s;
    uint16_t resolution_mm;
} ld2450_target_t;

typedef struct {
    uint8_t target_count;
    ld2450_target_t targets[LD2450_MAX_TARGETS];
} ld2450_frame_t;

typedef enum {
    LD2450_PARSE_OK = 0,
    LD2450_PARSE_INVALID_ARGUMENT,
    LD2450_PARSE_INVALID_LENGTH,
    LD2450_PARSE_INVALID_HEADER,
    LD2450_PARSE_INVALID_FOOTER
} ld2450_parse_result_t;

ld2450_parse_result_t ld2450_parse_frame(
    const uint8_t *data,
    size_t data_length,
    ld2450_frame_t *output
);

#endif /* LD2450_PARSER_H */
