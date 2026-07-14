#include "role_tx.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_log.h"

#include "lwip/inet.h"
#include "lwip/sockets.h"

#include "vsense_config.h"
#include "vsense_wifi.h"

static const char *TAG = "VSENSE_TX";

static void vsense_tx_task(void *arg)
{
    (void)arg;

    vsense_wifi_connect_sta();

    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);

    if (sock < 0) {
        ESP_LOGE(TAG, "Failed to create UDP socket.");
        vTaskDelete(NULL);
        return;
    }

    struct sockaddr_in dest_addr = {0};
    dest_addr.sin_family = AF_INET;
    dest_addr.sin_port = htons(VSENSE_TX_TARGET_PORT);
    dest_addr.sin_addr.s_addr = inet_addr(VSENSE_RX_IP);

    uint32_t packets_sent = 0;
    uint32_t last_logged_count = 0;

    const TickType_t delay_ticks = pdMS_TO_TICKS(1000 / VSENSE_PACKET_RATE_HZ);

    ESP_LOGI(TAG, "TX UDP task started.");
    ESP_LOGI(TAG, "Target IP: %s", VSENSE_RX_IP);
    ESP_LOGI(TAG, "Target port: %d", VSENSE_TX_TARGET_PORT);
    ESP_LOGI(TAG, "Target packet rate: %d Hz", VSENSE_PACKET_RATE_HZ);

    while (1) {
        char payload[64];

        int len = snprintf(
            payload,
            sizeof(payload),
            "vsense seq=%lu node=%s",
            (unsigned long)packets_sent,
            VSENSE_NODE_ID
        );

        int sent = sendto(
            sock,
            payload,
            len,
            0,
            (struct sockaddr *)&dest_addr,
            sizeof(dest_addr)
        );

        if (sent < 0) {
            ESP_LOGW(TAG, "UDP send failed.");
        } else {
            packets_sent++;
        }

        if ((packets_sent - last_logged_count) >= VSENSE_PACKET_RATE_HZ) {
            ESP_LOGI(
                TAG,
                "TX packets_sent=%lu target_rate=%dHz",
                (unsigned long)packets_sent,
                VSENSE_PACKET_RATE_HZ
            );

            last_logged_count = packets_sent;
        }

        vTaskDelay(delay_ticks);
    }
}

void vsense_role_tx_start(void)
{
    ESP_LOGI(TAG, "TX role selected.");
    ESP_LOGI(TAG, "TX will connect to Wi-Fi and send UDP packets at ~%d Hz.", VSENSE_PACKET_RATE_HZ);

    xTaskCreate(
        vsense_tx_task,
        "vsense_tx_task",
        6144,
        NULL,
        5,
        NULL
    );
}