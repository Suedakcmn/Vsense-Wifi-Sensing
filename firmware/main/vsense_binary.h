#ifndef VSENSE_BINARY_H
#define VSENSE_BINARY_H

#include <stddef.h>
#include <stdint.h>

#define VSENSE_CSI_BINARY_VERSION 1U
#define VSENSE_CSI_BINARY_HEADER_SIZE 24U

size_t vsense_binary_encode_csi(
    uint8_t *output,
    size_t output_size,
    uint32_t frame_count,
    uint64_t ts_us,
    int8_t rssi,
    uint8_t channel,
    const int8_t *csi,
    uint16_t csi_len
);

#endif /* VSENSE_BINARY_H */
