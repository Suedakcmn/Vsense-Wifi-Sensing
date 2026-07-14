#include "role_rx.h"

#include <stdint.h>
#include <string.h>
#include <unistd.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_err.h"
#include "esp_log.h"
#include "esp_wifi.h"

#include "lwip/inet.h"
#include "lwip/sockets.h"

#include "vsense_config.h"
#include "vsense_wifi.h"

static const char *TAG = "VSENSE_RX";

static volatile uint32_t s_csi_frames_received = 0;
static uint32_t s_last_logged_csi_count = 0;

static void vsense_rx_csi_callback(void *ctx, wifi_csi_info_t *data)
{
    (void)ctx;

    if (data == NULL || data->buf == NULL) {
        return;
    }

    s_csi_frames_received++;

    if ((s_csi_frames_received - s_last_logged_csi_count) >= 100) {
        ESP_LOGI(
            TAG,
            "CSI frames_received=%lu len=%d rssi=%d channel=%d",
            (unsigned long)s_csi_frames_received,
            data->len,
            data->rx_ctrl.rssi,
            data->rx_ctrl.channel
        );

        s_last_logged_csi_count = s_csi_frames_received;
    }
}

static void vsense_rx_csi_init(void)
{
    wifi_csi_config_t csi_config = {
        .lltf_en = true,
        .htltf_en = true,
        .stbc_htltf2_en = false,
        .ltf_merge_en = true,
        .channel_filter_en = true,
        .manu_scale = false,
        .shift = 0,
        .dump_ack_en = false,
    };

    esp_err_t err;

    err = esp_wifi_set_promiscuous(true);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "esp_wifi_set_promiscuous failed: %s", esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "Wi-Fi promiscuous mode enabled.");
    }

    err = esp_wifi_set_csi_rx_cb(vsense_rx_csi_callback, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_set_csi_rx_cb failed: %s", esp_err_to_name(err));
        return;
    }

    err = esp_wifi_set_csi_config(&csi_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_set_csi_config failed: %s", esp_err_to_name(err));
        ESP_LOGW(TAG, "CSI disabled, but UDP RX will continue.");
        return;
    }

    err = esp_wifi_set_csi(true);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_set_csi failed: %s", esp_err_to_name(err));
        ESP_LOGW(TAG, "CSI disabled, but UDP RX will continue.");
        return;
    }

    ESP_LOGI(TAG, "CSI collection enabled.");
}

static void vsense_rx_udp_task(void *arg)
{
    (void)arg;

    vsense_wifi_connect_sta();
    vsense_rx_csi_init();

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
    ESP_LOGI(TAG, "RX will enable CSI collection after Wi-Fi connection.");

    xTaskCreate(
        vsense_rx_udp_task,
        "vsense_rx_udp_task",
        8192,
        NULL,
        5,
        NULL
    );
}