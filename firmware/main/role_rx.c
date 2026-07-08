#include "role_rx.h"

#include "esp_log.h"
#include "vsense_config.h"

static const char *TAG = "VSENSE_RX";

void vsense_role_rx_start(void)
{
    ESP_LOGI(TAG, "RX role selected.");
    ESP_LOGI(TAG, "Future responsibility: enable CSI collection on Wi-Fi channel %d.", VSENSE_WIFI_CHANNEL);
    ESP_LOGI(TAG, "Future responsibility: forward CSI frames to collector via UDP/MQTT.");
}
