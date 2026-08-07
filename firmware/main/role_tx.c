#include "role_tx.h"

#include <stdbool.h>
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

typedef struct {
    const char *node_id;
    const char *ip;
    struct sockaddr_in address;
    uint32_t packets_sent;
    uint32_t packets_failed;
} vsense_tx_target_t;

static bool vsense_tx_target_init(
    vsense_tx_target_t *target,
    const char *node_id,
    const char *ip
)
{
    memset(target, 0, sizeof(*target));

    target->node_id = node_id;
    target->ip = ip;
    target->address.sin_family = AF_INET;
    target->address.sin_port = htons(VSENSE_TX_TARGET_PORT);

    if (
        inet_pton(
            AF_INET,
            ip,
            &target->address.sin_addr
        ) != 1
    ) {
        ESP_LOGE(
            TAG,
            "Invalid target IP for %s: %s",
            node_id,
            ip
        );
        return false;
    }

    return true;
}

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

    vsense_tx_target_t targets[2];
    size_t target_count = 0;

    if (
        vsense_tx_target_init(
            &targets[target_count],
            "rx_01",
            VSENSE_RX_01_IP
        )
    ) {
        target_count++;
    }

#if VSENSE_RX_02_ENABLED
    if (
        vsense_tx_target_init(
            &targets[target_count],
            "rx_02",
            VSENSE_RX_02_IP
        )
    ) {
        target_count++;
    }
#endif

    if (target_count == 0) {
        ESP_LOGE(TAG, "No valid RX targets configured.");
        close(sock);
        vTaskDelete(NULL);
        return;
    }

    uint32_t cycles_completed = 0;

    const TickType_t delay_ticks = pdMS_TO_TICKS(1000 / VSENSE_PACKET_RATE_HZ);

    ESP_LOGI(TAG, "TX UDP task started.");
    ESP_LOGI(TAG, "Target port: %d", VSENSE_TX_TARGET_PORT);
    ESP_LOGI(TAG, "Target packet rate: %d Hz", VSENSE_PACKET_RATE_HZ);

    for (size_t i = 0; i < target_count; i++) {
        ESP_LOGI(
            TAG,
            "Target %s configured: %s:%d",
            targets[i].node_id,
            targets[i].ip,
            VSENSE_TX_TARGET_PORT
        );
    }

    while (1) {
        char payload[64];

        int len = snprintf(
            payload,
            sizeof(payload),
            "vsense seq=%lu node=%s",
            (unsigned long)cycles_completed,
            VSENSE_NODE_ID
        );

        for (size_t i = 0; i < target_count; i++) {
            int sent = sendto(
                sock,
                payload,
                len,
                0,
                (struct sockaddr *)&targets[i].address,
                sizeof(targets[i].address)
            );

            if (sent == len) {
                targets[i].packets_sent++;
            } else {
                targets[i].packets_failed++;
            }
        }

        cycles_completed++;

        if ((cycles_completed % VSENSE_PACKET_RATE_HZ) == 0) {
            for (size_t i = 0; i < target_count; i++) {
                ESP_LOGI(
                    TAG,
                    "TX target=%s cycles=%lu sent=%lu failed=%lu",
                    targets[i].node_id,
                    (unsigned long)cycles_completed,
                    (unsigned long)targets[i].packets_sent,
                    (unsigned long)targets[i].packets_failed
                );
            }
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
