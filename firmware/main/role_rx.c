#include "role_rx.h"

#include <stdint.h>
#include <string.h>
#include <unistd.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_log.h"

#include "lwip/inet.h"
#include "lwip/sockets.h"

#include "vsense_config.h"
#include "vsense_wifi.h"

static const char *TAG = "VSENSE_RX";

static void vsense_rx_udp_task(void *arg)
{
    (void)arg;

    vsense_wifi_connect_sta();

    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);

    if (sock < 0) {
        ESP_LOGE(TAG, "Failed to create UDP socket.");
        vTaskDelete(NULL);
        return;
    }

    struct sockaddr_in listen_addr = {0};
    listen_addr.sin_family = AF_INET;
    listen_addr.sin_addr.s_addr = htonl(INADDR_ANY);
    listen_addr.sin_port = htons(VSENSE_RX_UDP_PORT);

    int bind_result = bind(sock, (struct sockaddr *)&listen_addr, sizeof(listen_addr));

    if (bind_result < 0) {
        ESP_LOGE(TAG, "UDP bind failed on port %d.", VSENSE_RX_UDP_PORT);
        close(sock);
        vTaskDelete(NULL);
        return;
    }

    ESP_LOGI(TAG, "RX UDP server listening on port %d.", VSENSE_RX_UDP_PORT);

    uint32_t packets_received = 0;
    uint32_t last_logged_count = 0;

    while (1) {
        char rx_buffer[128];

        struct sockaddr_in source_addr = {0};
        socklen_t socklen = sizeof(source_addr);

        int len = recvfrom(
            sock,
            rx_buffer,
            sizeof(rx_buffer) - 1,
            0,
            (struct sockaddr *)&source_addr,
            &socklen
        );

        if (len < 0) {
            ESP_LOGW(TAG, "UDP receive failed.");
            continue;
        }

        rx_buffer[len] = '\0';
        packets_received++;

        if ((packets_received - last_logged_count) >= 100) {
            ESP_LOGI(
                TAG,
                "RX packets_received=%lu last_payload=\"%s\"",
                (unsigned long)packets_received,
                rx_buffer
            );

            last_logged_count = packets_received;
        }
    }
}

void vsense_role_rx_start(void)
{
    ESP_LOGI(TAG, "RX role selected.");
    ESP_LOGI(TAG, "RX will connect to Wi-Fi and listen on UDP port %d.", VSENSE_RX_UDP_PORT);
    ESP_LOGI(TAG, "CSI callback will be added after live UDP link works.");

    xTaskCreate(
        vsense_rx_udp_task,
        "vsense_rx_udp_task",
        6144,
        NULL,
        5,
        NULL
    );
}