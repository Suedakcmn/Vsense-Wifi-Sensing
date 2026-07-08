#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_log.h"

#include "vsense_config.h"
#include "role_tx.h"
#include "role_rx.h"

static const char *TAG = "VSENSE_APP";

void app_main(void)
{
    ESP_LOGI(TAG, "VSense firmware skeleton starting...");
    ESP_LOGI(TAG, "Node ID: %s", VSENSE_NODE_ID);
    ESP_LOGI(TAG, "Configured role: %s", VSENSE_NODE_ROLE);
    ESP_LOGI(TAG, "Wi-Fi channel: %d", VSENSE_WIFI_CHANNEL);
    ESP_LOGI(TAG, "Packet rate target: %d Hz", VSENSE_PACKET_RATE_HZ);

    if (strcmp(VSENSE_NODE_ROLE, "TX") == 0) {
        vsense_role_tx_start();
    } else if (strcmp(VSENSE_NODE_ROLE, "RX") == 0) {
        vsense_role_rx_start();
    } else {
        ESP_LOGW(TAG, "Unknown VSENSE_NODE_ROLE: %s", VSENSE_NODE_ROLE);
        ESP_LOGW(TAG, "Please set VSENSE_NODE_ROLE to either \"TX\" or \"RX\".");
    }

    while (1) {
        ESP_LOGI(TAG, "VSense node alive. Role=%s NodeID=%s", VSENSE_NODE_ROLE, VSENSE_NODE_ID);
        vTaskDelay(pdMS_TO_TICKS(10000));
    }
}
