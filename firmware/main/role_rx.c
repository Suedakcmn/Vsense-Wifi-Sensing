git merge origin/main --allow-unrelated-histories --no-commit#include "role_rx.h"

#include <stddef.h>
#include <stdint.h>

#include "esp_log.h"
#include "vsense_config.h"

static const char *TAG = "VSENSE_RX";

static void vsense_rx_wifi_init_placeholder(void)
{
    /*
     * Week 1 skeleton:
     * Real Wi-Fi initialization is not implemented yet.
     *
     * Week 2 hardware step:
     * Configure ESP32-S3 Wi-Fi mode, channel, MAC filtering, and RX behavior here.
     */
    ESP_LOGI(TAG, "Wi-Fi init placeholder.");
    ESP_LOGI(TAG, "Future Wi-Fi channel: %d", VSENSE_WIFI_CHANNEL);
}

static void vsense_rx_csi_init_placeholder(void)
{
    /*
     * Week 1 skeleton:
     * Real ESP-IDF CSI API calls are not enabled yet.
     *
     * Week 2 hardware step:
     * Add esp_wifi_set_csi_config, esp_wifi_set_csi_rx_cb, and esp_wifi_set_csi here.
     */
    ESP_LOGI(TAG, "CSI init placeholder.");
    ESP_LOGI(TAG, "Future responsibility: enable ESP32-S3 CSI callback.");
}

static void vsense_rx_csi_callback_placeholder(
    const int8_t *csi_payload,
    size_t csi_len,
    int rssi,
    int channel
)
{
    /*
     * Week 1 skeleton:
     * This function documents the future CSI callback shape.
     *
     * Expected future fields:
     * - timestamp
     * - RSSI
     * - Wi-Fi channel
     * - CSI payload length
     * - raw CSI payload
     */
    (void)csi_payload;

    ESP_LOGI(
        TAG,
        "CSI callback placeholder: csi_len=%u rssi=%d channel=%d",
        (unsigned int)csi_len,
        rssi,
        channel
    );
}

void vsense_role_rx_start(void)
{
    ESP_LOGI(TAG, "RX role selected.");
    ESP_LOGI(TAG, "Future responsibility: enable CSI collection on Wi-Fi channel %d.", VSENSE_WIFI_CHANNEL);
    ESP_LOGI(TAG, "Future responsibility: forward CSI frames to collector via UDP/MQTT.");

    vsense_rx_wifi_init_placeholder();
    vsense_rx_csi_init_placeholder();

    /*
     * Build-only placeholder call so the callback skeleton is compiled and checked.
     * This does not represent real CSI data.
     */
    vsense_rx_csi_callback_placeholder(NULL, 0, 0, VSENSE_WIFI_CHANNEL);
}
