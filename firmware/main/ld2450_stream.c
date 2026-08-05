#include "ld2450_stream.h"

#include <string.h>

static const uint8_t LD2450_HEADER[] = {0xAA, 0xFF, 0x03, 0x00};

static size_t ld2450_stream_retained_suffix(
    const uint8_t *data,
    size_t data_length
)
{
    size_t maximum = sizeof(LD2450_HEADER) - 1;
    if (maximum > data_length) {
        maximum = data_length;
    }

    for (size_t length = maximum; length > 0; length--) {
        if (
            memcmp(
                &data[data_length - length],
                LD2450_HEADER,
                length
            ) == 0
        ) {
            return length;
        }
    }

    return 0;
}

void ld2450_stream_init(ld2450_stream_t *stream)
{
    if (stream != NULL) {
        memset(stream, 0, sizeof(*stream));
    }
}

bool ld2450_stream_push_byte(
    ld2450_stream_t *stream,
    uint8_t byte,
    uint8_t output[LD2450_DATA_FRAME_SIZE]
)
{
    if (stream == NULL || output == NULL) {
        return false;
    }

    if (stream->length < sizeof(LD2450_HEADER)) {
        if (byte == LD2450_HEADER[stream->length]) {
            stream->buffer[stream->length++] = byte;
        } else if (byte == LD2450_HEADER[0]) {
            stream->buffer[0] = byte;
            stream->length = 1;
        } else {
            stream->length = 0;
        }

        return false;
    }

    stream->buffer[stream->length++] = byte;

    if (stream->length < LD2450_DATA_FRAME_SIZE) {
        return false;
    }

    memcpy(output, stream->buffer, LD2450_DATA_FRAME_SIZE);

    size_t retained = ld2450_stream_retained_suffix(
        &stream->buffer[1],
        LD2450_DATA_FRAME_SIZE - 1
    );

    if (retained > 0) {
        memcpy(
            stream->buffer,
            &stream->buffer[LD2450_DATA_FRAME_SIZE - retained],
            retained
        );
    }
    stream->length = retained;

    return true;
}
