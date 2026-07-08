#include "role_tx.h"

#include "esp_log.h"
#include "vsense_config.h"

static const char *TAG = "VSENSE_TX";

void vsense_role_tx_start(void)
{
    ESP_LOGI(TAG, "TX role selected.");
    ESP_LOGI(TAG, "Future responsibility: send Wi-Fi packets at ~%d Hz.", VSENSE_PACKET_RATE_HZ);
    ESP_LOGI(TAG, "Future responsibility: support unicast packet transmission to RX/collector.");
}
