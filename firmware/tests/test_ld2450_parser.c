#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "ld2450_parser.h"

static const uint8_t OFFICIAL_EXAMPLE_FRAME[LD2450_DATA_FRAME_SIZE] = {
    0xAA, 0xFF, 0x03, 0x00,

    0x0E, 0x03,
    0xB1, 0x86,
    0x10, 0x00,
    0x40, 0x01,

    0x00, 0x00,
    0x00, 0x00,
    0x00, 0x00,
    0x00, 0x00,

    0x00, 0x00,
    0x00, 0x00,
    0x00, 0x00,
    0x00, 0x00,

    0x55, 0xCC
};

static void test_official_example(void)
{
    ld2450_frame_t output;

    ld2450_parse_result_t result = ld2450_parse_frame(
        OFFICIAL_EXAMPLE_FRAME,
        sizeof(OFFICIAL_EXAMPLE_FRAME),
        &output
    );

    assert(result == LD2450_PARSE_OK);
    assert(output.target_count == 1);

    assert(output.targets[0].target_id == 1);
    assert(output.targets[0].present);
    assert(output.targets[0].x_mm == -782);
    assert(output.targets[0].y_mm == 1713);
    assert(output.targets[0].speed_cm_s == -16);
    assert(output.targets[0].resolution_mm == 320);

    assert(output.targets[1].target_id == 2);
    assert(!output.targets[1].present);

    assert(output.targets[2].target_id == 3);
    assert(!output.targets[2].present);
}

static void test_empty_frame(void)
{
    uint8_t empty_frame[LD2450_DATA_FRAME_SIZE] = {
        0xAA, 0xFF, 0x03, 0x00
    };

    empty_frame[28] = 0x55;
    empty_frame[29] = 0xCC;

    ld2450_frame_t output;

    ld2450_parse_result_t result = ld2450_parse_frame(
        empty_frame,
        sizeof(empty_frame),
        &output
    );

    assert(result == LD2450_PARSE_OK);
    assert(output.target_count == 0);

    assert(!output.targets[0].present);
    assert(!output.targets[1].present);
    assert(!output.targets[2].present);
}

static void test_invalid_length(void)
{
    ld2450_frame_t output;

    ld2450_parse_result_t result = ld2450_parse_frame(
        OFFICIAL_EXAMPLE_FRAME,
        LD2450_DATA_FRAME_SIZE - 1,
        &output
    );

    assert(result == LD2450_PARSE_INVALID_LENGTH);
}

static void test_invalid_header(void)
{
    uint8_t invalid_frame[LD2450_DATA_FRAME_SIZE];

    memcpy(
        invalid_frame,
        OFFICIAL_EXAMPLE_FRAME,
        sizeof(invalid_frame)
    );

    invalid_frame[0] = 0x00;

    ld2450_frame_t output;

    ld2450_parse_result_t result = ld2450_parse_frame(
        invalid_frame,
        sizeof(invalid_frame),
        &output
    );

    assert(result == LD2450_PARSE_INVALID_HEADER);
}

static void test_invalid_footer(void)
{
    uint8_t invalid_frame[LD2450_DATA_FRAME_SIZE];

    memcpy(
        invalid_frame,
        OFFICIAL_EXAMPLE_FRAME,
        sizeof(invalid_frame)
    );

    invalid_frame[29] = 0x00;

    ld2450_frame_t output;

    ld2450_parse_result_t result = ld2450_parse_frame(
        invalid_frame,
        sizeof(invalid_frame),
        &output
    );

    assert(result == LD2450_PARSE_INVALID_FOOTER);
}

static void test_invalid_arguments(void)
{
    ld2450_frame_t output;

    assert(
        ld2450_parse_frame(
            NULL,
            LD2450_DATA_FRAME_SIZE,
            &output
        ) == LD2450_PARSE_INVALID_ARGUMENT
    );

    assert(
        ld2450_parse_frame(
            OFFICIAL_EXAMPLE_FRAME,
            LD2450_DATA_FRAME_SIZE,
            NULL
        ) == LD2450_PARSE_INVALID_ARGUMENT
    );
}

int main(void)
{
    test_official_example();
    test_empty_frame();
    test_invalid_length();
    test_invalid_header();
    test_invalid_footer();
    test_invalid_arguments();

    puts("All LD2450 parser tests passed.");

    return 0;
}