#include "ld2450_parser.h"

#include <string.h>

static const uint8_t LD2450_FRAME_HEADER[] = {
    0xAA, 0xFF, 0x03, 0x00
};

static const uint8_t LD2450_FRAME_FOOTER[] = {
    0x55, 0xCC
};

static uint16_t ld2450_read_uint16_le(const uint8_t *data)
{
    return (uint16_t)data[0] |
           ((uint16_t)data[1] << 8);
}

static int16_t ld2450_decode_signed_value(const uint8_t *data)
{
    uint16_t raw_value = ld2450_read_uint16_le(data);
    int16_t magnitude = (int16_t)(raw_value & 0x7FFF);

    if ((raw_value & 0x8000) != 0) {
        return magnitude;
    }

    return (int16_t)(-magnitude);
}

static bool ld2450_target_block_is_empty(const uint8_t *data)
{
    for (size_t index = 0; index < LD2450_TARGET_BLOCK_SIZE; index++) {
        if (data[index] != 0) {
            return false;
        }
    }

    return true;
}

ld2450_parse_result_t ld2450_parse_frame(
    const uint8_t *data,
    size_t data_length,
    ld2450_frame_t *output
)
{
    if (data == NULL || output == NULL) {
        return LD2450_PARSE_INVALID_ARGUMENT;
    }

    if (data_length != LD2450_DATA_FRAME_SIZE) {
        return LD2450_PARSE_INVALID_LENGTH;
    }

    memset(output, 0, sizeof(*output));

    if (
        memcmp(
            data,
            LD2450_FRAME_HEADER,
            sizeof(LD2450_FRAME_HEADER)
        ) != 0
    ) {
        return LD2450_PARSE_INVALID_HEADER;
    }

    if (
        memcmp(
            &data[LD2450_DATA_FRAME_SIZE - sizeof(LD2450_FRAME_FOOTER)],
            LD2450_FRAME_FOOTER,
            sizeof(LD2450_FRAME_FOOTER)
        ) != 0
    ) {
        return LD2450_PARSE_INVALID_FOOTER;
    }

    for (
        size_t target_index = 0;
        target_index < LD2450_MAX_TARGETS;
        target_index++
    ) {
        size_t target_offset =
            sizeof(LD2450_FRAME_HEADER) +
            (target_index * LD2450_TARGET_BLOCK_SIZE);

        const uint8_t *target_data = &data[target_offset];
        ld2450_target_t *target = &output->targets[target_index];

        target->target_id = (uint8_t)(target_index + 1);
        target->present = !ld2450_target_block_is_empty(target_data);

        if (!target->present) {
            continue;
        }

        target->x_mm =
            ld2450_decode_signed_value(&target_data[0]);

        target->y_mm =
            ld2450_decode_signed_value(&target_data[2]);

        target->speed_cm_s =
            ld2450_decode_signed_value(&target_data[4]);

        target->resolution_mm =
            ld2450_read_uint16_le(&target_data[6]);

        output->target_count++;
    }

    return LD2450_PARSE_OK;
}
