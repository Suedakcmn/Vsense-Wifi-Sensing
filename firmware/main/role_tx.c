#include "role_tx.h"

#include <stdint.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_log.h"
#include "vsense_config.h"

static const char *TAG = "VSENSE_TX";

static void vsense_tx_task(void *arg)
{
    (void)arg;

    uint32_t simulated_packet_count = 0;
    uint32_t last_logged_count = 0;

    const TickType_t delay_ticks = pdMS_TO_TICKS(1000 / VSENSE_PACKET_RATE_HZ);

    ESP_LOGI(TAG, "TX task started.");
    ESP_LOGI(TAG, "Target packet rate: %d Hz", VSENSE_PACKET_RATE_HZ);

    while (1) {
        /*
         * Week 1 skeleton:
         * This counter simulates the timing of future Wi-Fi packet transmission.
         *
         * Week 2 hardware step:
         * Replace this counter increment with real Wi-Fi packet sending.
         */
        simulated_packet_count++;

        if ((simulated_packet_count - last_logged_count) >= VSENSE_PACKET_RATE_HZ) {
            ESP_LOGI(
                TAG,
                "TX heartbeat: simulated_packets=%lu target_rate=%dHz",
                (unsigned long)simulated_packet_count,
                VSENSE_PACKET_RATE_HZ
            );

            last_logged_count = simulated_packet_count;
        }

        vTaskDelay(delay_ticks);
    }
}

void vsense_role_tx_start(void)
{
    ESP_LOGI(TAG, "TX role selected.");
    ESP_LOGI(TAG, "Future responsibility: send Wi-Fi packets at ~%d Hz.", VSENSE_PACKET_RATE_HZ);
    ESP_LOGI(TAG, "Future responsibility: support unicast packet transmission to RX/collector.");

    xTaskCreate(
        vsense_tx_task,
        "vsense_tx_task",
        4096,
        NULL,
        5,
        NULL
    );
}
