#include "vsense_binary.h"

#include <string.h>

#define VSENSE_CSI_BINARY_FLAGS 0U

static void vsense_write_u16_le(uint8_t *output, uint16_t value)
{
    output[0] = (uint8_t)(value & 0xffU);
    output[1] = (uint8_t)((value >> 8) & 0xffU);
}

static void vsense_write_u32_le(uint8_t *output, uint32_t value)
{
    for (size_t index = 0; index < sizeof(value); index++) {
        output[index] = (uint8_t)(value >> (index * 8U));
    }
}

static void vsense_write_u64_le(uint8_t *output, uint64_t value)
{
    for (size_t index = 0; index < sizeof(value); index++) {
        output[index] = (uint8_t)(value >> (index * 8U));
    }
}

size_t vsense_binary_encode_csi(
    uint8_t *output,
    size_t output_size,
    uint32_t frame_count,
    uint64_t ts_us,
    int8_t rssi,
    uint8_t channel,
    const int8_t *csi,
    uint16_t csi_len
)
{
    const size_t packet_size = VSENSE_CSI_BINARY_HEADER_SIZE + csi_len;

    if (
        output == NULL ||
        csi == NULL ||
        output_size < packet_size
    ) {
        return 0;
    }

    memcpy(output, "VSCS", 4);
    output[4] = VSENSE_CSI_BINARY_VERSION;
    output[5] = VSENSE_CSI_BINARY_FLAGS;
    vsense_write_u16_le(&output[6], VSENSE_CSI_BINARY_HEADER_SIZE);
    vsense_write_u32_le(&output[8], frame_count);
    vsense_write_u64_le(&output[12], ts_us);
    output[20] = (uint8_t)rssi;
    output[21] = channel;
    vsense_write_u16_le(&output[22], csi_len);
    memcpy(&output[VSENSE_CSI_BINARY_HEADER_SIZE], csi, csi_len);

    return packet_size;
}
