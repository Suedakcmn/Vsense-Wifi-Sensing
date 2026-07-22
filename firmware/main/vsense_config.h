#ifndef VSENSE_CONFIG_H
#define VSENSE_CONFIG_H

/*
 * VSense firmware configuration.
 *
 * This file is intentionally simple for Week 1.
 * Later, these values can move to menuconfig/Kconfig or sdkconfig.defaults.
 */

#define VSENSE_NODE_ID              "node_01"

/*
 * Select node role:
 * - "TX": transmitter node, will send Wi-Fi packets
 * - "RX": receiver node, will collect CSI
 */
#define VSENSE_NODE_ROLE            "RX"

#define VSENSE_WIFI_CHANNEL         6
#define VSENSE_PACKET_RATE_HZ       100
#define VSENSE_WIFI_SSID            "change me"
#define VSENSE_WIFI_PASSWORD        "change me"
#define VSENSE_RX_UDP_PORT          3333
#define VSENSE_RX_IP                "192.168.128.35"
#define VSENSE_TX_TARGET_PORT       3333

#define VSENSE_COLLECTOR_IP         "192.168.128.96"
#define VSENSE_COLLECTOR_UDP_PORT   4444

#define VSENSE_MQTT_BROKER_URI      "mqtt://127.0.0.1"
#define VSENSE_MQTT_TOPIC_CSI       "vsense/node_01/csi"
#define VSENSE_MQTT_TOPIC_HEALTH    "vsense/node_01/health"

/*
 * CSI buffer size placeholder.
 * Real value will be adjusted after testing with ESP32-S3 CSI output.
 */
#define VSENSE_CSI_BUFFER_MAX_LEN   384

#endif /* VSENSE_CONFIG_H */
