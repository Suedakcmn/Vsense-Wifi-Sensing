#ifndef VSENSE_MQTT_H
#define VSENSE_MQTT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

void vsense_mqtt_start(void);

bool vsense_mqtt_is_connected(void);

bool vsense_mqtt_publish_message(
    const char *topic,
    const char *payload,
    size_t payload_length,
    int qos,
    bool retain
);

bool vsense_mqtt_publish_health(
    uint64_t uptime_ms,
    uint32_t free_heap,
    uint32_t minimum_free_heap,
    uint32_t udp_packets,
    uint32_t csi_callbacks,
    uint32_t csi_filtered,
    uint32_t csi_length_filtered,
    uint32_t csi_received,
    uint32_t csi_queued,
    uint32_t csi_sent,
    uint32_t csi_pps,
    uint32_t csi_forwarded_pps,
    uint32_t udp_csi_sent,
    uint32_t udp_csi_failed,
    uint32_t mqtt_csi_published,
    uint32_t mqtt_csi_failed,
    uint32_t csi_dropped,
    uint32_t csi_oversized,
    uint32_t queue_depth,
    uint32_t expected_csi_length,
    uint32_t raw_send_every_n_frames,
    int8_t last_rssi
);


bool vsense_mqtt_publish_csi(
    const void *payload,
    size_t payload_length
);

#endif /* VSENSE_MQTT_H */
