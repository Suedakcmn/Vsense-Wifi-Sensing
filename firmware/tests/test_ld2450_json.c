#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "ld2450_json.h"

static void test_empty_targets(void)
{
    ld2450_frame_t frame = {0};
    char payload[256];
    size_t payload_length = 0;

    assert(ld2450_format_ground_truth_json(
        "ld2450_01",
        123,
        4,
        &frame,
        payload,
        sizeof(payload),
        &payload_length
    ));

    const char *expected =
        "{\"schema_version\":1,"
        "\"message_type\":\"ground_truth\","
        "\"node_id\":\"ld2450_01\","
        "\"ts_us\":123,"
        "\"frame_seq\":4,"
        "\"targets\":[]}";

    assert(payload_length == strlen(expected));
    assert(strcmp(payload, expected) == 0);
}

static void test_multiple_targets_and_derived_distance(void)
{
    ld2450_frame_t frame = {0};
    frame.target_count = 2;
    frame.targets[0] = (ld2450_target_t){
        .target_id = 1,
        .present = true,
        .x_mm = 300,
        .y_mm = 400,
        .speed_cm_s = -7,
        .resolution_mm = 320,
    };
    frame.targets[2] = (ld2450_target_t){
        .target_id = 3,
        .present = true,
        .x_mm = -5,
        .y_mm = 12,
        .speed_cm_s = 2,
        .resolution_mm = 75,
    };

    char payload[512];
    size_t payload_length = 0;
    assert(ld2450_format_ground_truth_json(
        "ld2450_01",
        UINT64_C(123456789),
        42,
        &frame,
        payload,
        sizeof(payload),
        &payload_length
    ));

    assert(strstr(payload, "\"distance_mm\":500") != NULL);
    assert(strstr(payload, "\"distance_mm\":13") != NULL);
    assert(strstr(payload, "},{\"target_id\":3") != NULL);
    assert(payload_length == strlen(payload));
}

static void test_rejects_invalid_arguments_and_small_buffer(void)
{
    ld2450_frame_t frame = {0};
    char payload[16];
    size_t payload_length = 0;

    assert(!ld2450_format_ground_truth_json(
        NULL, 0, 0, &frame, payload, sizeof(payload), &payload_length
    ));
    assert(!ld2450_format_ground_truth_json(
        "ld2450_01", 0, 0, NULL, payload, sizeof(payload), &payload_length
    ));
    assert(!ld2450_format_ground_truth_json(
        "ld2450_01", 0, 0, &frame, payload, sizeof(payload), &payload_length
    ));
}

int main(void)
{
    test_empty_targets();
    test_multiple_targets_and_derived_distance();
    test_rejects_invalid_arguments_and_small_buffer();

    puts("All LD2450 JSON tests passed.");
    return 0;
}
