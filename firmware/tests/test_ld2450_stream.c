#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "ld2450_stream.h"

static const uint8_t VALID_FRAME[LD2450_DATA_FRAME_SIZE] = {
    0xAA, 0xFF, 0x03, 0x00,
    0x0E, 0x03, 0xB1, 0x86, 0x10, 0x00, 0x40, 0x01,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x55, 0xCC
};

static size_t feed_bytes(
    ld2450_stream_t *stream,
    const uint8_t *data,
    size_t data_length,
    uint8_t output[LD2450_DATA_FRAME_SIZE]
)
{
    size_t frames = 0;

    for (size_t index = 0; index < data_length; index++) {
        if (ld2450_stream_push_byte(stream, data[index], output)) {
            frames++;
        }
    }

    return frames;
}

static void test_complete_frame(void)
{
    ld2450_stream_t stream;
    ld2450_stream_init(&stream);
    uint8_t output[LD2450_DATA_FRAME_SIZE];

    assert(feed_bytes(
        &stream,
        VALID_FRAME,
        sizeof(VALID_FRAME),
        output
    ) == 1);
    assert(memcmp(output, VALID_FRAME, sizeof(output)) == 0);
}

static void test_fragmented_frame(void)
{
    ld2450_stream_t stream;
    ld2450_stream_init(&stream);
    uint8_t output[LD2450_DATA_FRAME_SIZE];

    assert(feed_bytes(&stream, VALID_FRAME, 7, output) == 0);
    assert(feed_bytes(&stream, &VALID_FRAME[7], 11, output) == 0);
    assert(feed_bytes(
        &stream,
        &VALID_FRAME[18],
        sizeof(VALID_FRAME) - 18,
        output
    ) == 1);
    assert(memcmp(output, VALID_FRAME, sizeof(output)) == 0);
}

static void test_noise_and_back_to_back_frames(void)
{
    ld2450_stream_t stream;
    ld2450_stream_init(&stream);
    uint8_t output[LD2450_DATA_FRAME_SIZE];
    const uint8_t noise[] = {0x00, 0xAA, 0xAA, 0x10, 0xFF};

    assert(feed_bytes(&stream, noise, sizeof(noise), output) == 0);
    assert(feed_bytes(
        &stream,
        VALID_FRAME,
        sizeof(VALID_FRAME),
        output
    ) == 1);
    assert(memcmp(output, VALID_FRAME, sizeof(output)) == 0);
    assert(feed_bytes(
        &stream,
        VALID_FRAME,
        sizeof(VALID_FRAME),
        output
    ) == 1);
}

static void test_invalid_candidate_then_valid_frame(void)
{
    ld2450_stream_t stream;
    ld2450_stream_init(&stream);
    uint8_t output[LD2450_DATA_FRAME_SIZE];
    uint8_t invalid[LD2450_DATA_FRAME_SIZE];
    memcpy(invalid, VALID_FRAME, sizeof(invalid));
    invalid[LD2450_DATA_FRAME_SIZE - 1] = 0x00;

    assert(feed_bytes(&stream, invalid, sizeof(invalid), output) == 1);
    assert(feed_bytes(
        &stream,
        VALID_FRAME,
        sizeof(VALID_FRAME),
        output
    ) == 1);
    assert(memcmp(output, VALID_FRAME, sizeof(output)) == 0);
}

static void test_dropped_byte_resynchronizes_on_next_header(void)
{
    ld2450_stream_t stream;
    ld2450_stream_init(&stream);
    uint8_t output[LD2450_DATA_FRAME_SIZE];

    assert(feed_bytes(
        &stream,
        VALID_FRAME,
        LD2450_DATA_FRAME_SIZE - 1,
        output
    ) == 0);

    assert(feed_bytes(
        &stream,
        VALID_FRAME,
        sizeof(VALID_FRAME),
        output
    ) == 2);
    assert(memcmp(output, VALID_FRAME, sizeof(output)) == 0);
}

int main(void)
{
    test_complete_frame();
    test_fragmented_frame();
    test_noise_and_back_to_back_frames();
    test_invalid_candidate_then_valid_frame();
    test_dropped_byte_resynchronizes_on_next_header();

    puts("All LD2450 stream tests passed.");
    return 0;
}
