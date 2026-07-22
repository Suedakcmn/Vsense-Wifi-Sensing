#ifndef VSENSE_MQTT_H
#define VSENSE_MQTT_H

#include <stdbool.h>
#include <stdint.h>

void vsense_mqtt_start(void);

bool vsense_mqtt_is_connected(void);

bool vsense_mqtt_publish_health(
    uint64_t uptime_ms,
    uint32_t free_heap,
    uint32_t minimum_free_heap,
    uint32_t udp_packets,
    uint32_t csi_received,
    uint32_t csi_queued,
    uint32_t csi_sent,
    uint32_t csi_dropped,
    uint32_t queue_depth,
    int8_t last_rssi
);

#endif /* VSENSE_MQTT_H */
