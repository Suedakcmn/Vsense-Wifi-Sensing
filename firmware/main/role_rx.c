#include "role_rx.h"
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

#include "esp_err.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_timer.h"
#include "esp_system.h"

#include "lwip/inet.h"
#include "lwip/sockets.h"

#include "vsense_config.h"
#include "vsense_wifi.h"

static const char *TAG = "VSENSE_RX";
static QueueHandle_t s_csi_queue = NULL;
static volatile uint32_t s_csi_frames_received = 0;
static volatile uint32_t s_csi_frames_queued = 0;
static volatile uint32_t s_csi_frames_sent = 0;
static volatile uint32_t s_csi_frames_dropped = 0;
static volatile uint32_t s_udp_packets_received = 0;
static volatile int8_t s_last_rssi = 0;


static int s_collector_sock = -1;
static struct sockaddr_in s_collector_addr;



#define VSENSE_MAX_CSI_LEN 256
#define VSENSE_CSI_QUEUE_LENGTH 8
#define VSENSE_RAW_SEND_EVERY_N_FRAMES 10

typedef struct {
    int64_t ts_us;
    uint32_t frame_count;
    int8_t rssi;
    uint8_t channel;
    uint16_t len;
    int8_t csi[VSENSE_MAX_CSI_LEN];
} vsense_csi_frame_t;


static void vsense_rx_health_task(void *arg)
{
    (void)arg;

    ESP_LOGI(TAG, "RX health telemetry task started.");

    while (true) {
        uint64_t uptime_ms = (uint64_t)(
            esp_timer_get_time() / 1000
        );

        uint32_t free_heap = esp_get_free_heap_size();
        uint32_t minimum_free_heap =
            esp_get_minimum_free_heap_size();

        UBaseType_t queue_depth = 0;

        if (s_csi_queue != NULL) {
            queue_depth = uxQueueMessagesWaiting(
                s_csi_queue
            );
        }

        ESP_LOGI(
            TAG,
            "HEALTH "
            "node_id=%s "
            "uptime_ms=%llu "
            "free_heap=%lu "
            "minimum_free_heap=%lu "
            "udp_packets=%lu "
            "csi_received=%lu "
            "csi_queued=%lu "
            "csi_sent=%lu "
            "csi_dropped=%lu "
            "queue_depth=%u "
            "last_rssi=%d",
            VSENSE_NODE_ID,
            (unsigned long long)uptime_ms,
            (unsigned long)free_heap,
            (unsigned long)minimum_free_heap,
            (unsigned long)s_udp_packets_received,
            (unsigned long)s_csi_frames_received,
            (unsigned long)s_csi_frames_queued,
            (unsigned long)s_csi_frames_sent,
            (unsigned long)s_csi_frames_dropped,
            (unsigned int)queue_depth,
            (int)s_last_rssi
        );

        vTaskDelay(
            pdMS_TO_TICKS(
                VSENSE_HEALTH_INTERVAL_MS
            )
        );
    }
}

static void vsense_rx_collector_init(void)
{
    s_collector_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);

    if (s_collector_sock < 0) {
        ESP_LOGE(TAG, "Failed to create collector UDP socket.");
        return;
    }

    memset(&s_collector_addr, 0, sizeof(s_collector_addr));
    s_collector_addr.sin_family = AF_INET;
    s_collector_addr.sin_port = htons(VSENSE_COLLECTOR_UDP_PORT);
    s_collector_addr.sin_addr.s_addr = inet_addr(VSENSE_COLLECTOR_IP);

    ESP_LOGI(
        TAG,
        "Collector target configured: %s:%d",
        VSENSE_COLLECTOR_IP,
        VSENSE_COLLECTOR_UDP_PORT
    );
}
static int vsense_build_raw_csi_json(
    char *output,
    size_t output_size,
    const vsense_csi_frame_t *frame
)
{
    if (output == NULL || frame == NULL || output_size == 0) {
        return -1;
    }

    int written = snprintf(
        output,
        output_size,
        "{\"ts_us\":%lld,"
        "\"node_id\":\"%s\","
        "\"frame_count\":%lu,"
        "\"rssi\":%d,"
        "\"channel\":%u,"
        "\"len\":%u,"
        "\"csi\":[",
        (long long)frame->ts_us,
        VSENSE_NODE_ID,
        (unsigned long)frame->frame_count,
        frame->rssi,
        frame->channel,
        frame->len
    );

    if (written < 0 || (size_t)written >= output_size) {
        return -1;
    }

    size_t offset = (size_t)written;

    for (uint16_t i = 0; i < frame->len; i++) {
        written = snprintf(
            output + offset,
            output_size - offset,
            i == 0 ? "%d" : ",%d",
            frame->csi[i]
        );

        if (written < 0 || (size_t)written >= output_size - offset) {
            return -1;
        }

        offset += (size_t)written;
    }

    written = snprintf(
        output + offset,
        output_size - offset,
        "]}"
    );

    if (written < 0 || (size_t)written >= output_size - offset) {
        return -1;
    }

    offset += (size_t)written;
    return (int)offset;
}
static void vsense_csi_sender_task(void *arg)
{
    (void)arg;

    vsense_csi_frame_t frame;
    char json_message[2048];

    ESP_LOGI(TAG, "Raw CSI sender task started.");

    while (true) {
        if (xQueueReceive(s_csi_queue, &frame, portMAX_DELAY) != pdTRUE) {
            continue;
        }

        if (s_collector_sock < 0) {
            s_csi_frames_dropped++;
            continue;
        }

        int message_len = vsense_build_raw_csi_json(
            json_message,
            sizeof(json_message),
            &frame
        );

        if (message_len <= 0) {
            ESP_LOGW(TAG, "Raw CSI JSON buffer was too small.");
            s_csi_frames_dropped++;
            continue;
        }

        int sent_len = sendto(
            s_collector_sock,
            json_message,
            message_len,
            0,
            (struct sockaddr *)&s_collector_addr,
            sizeof(s_collector_addr)
        );

        if (sent_len < 0) {
            ESP_LOGW(TAG, "Failed to send raw CSI frame.");
            s_csi_frames_dropped++;
            continue;
        }

        if (sent_len != message_len) {
            ESP_LOGW(
                TAG,
                "Incomplete raw CSI send: expected=%d sent=%d",
                message_len,
                sent_len
            );
            s_csi_frames_dropped++;
            continue;
        }

        s_csi_frames_sent++;

        if ((s_csi_frames_sent % 100) == 0) {
            ESP_LOGI(
                TAG,
                "Raw CSI sent=%lu queued=%lu dropped=%lu last_len=%u",
                (unsigned long)s_csi_frames_sent,
                (unsigned long)s_csi_frames_queued,
                (unsigned long)s_csi_frames_dropped,
                frame.len
            );
        }
    }
}

static void vsense_rx_csi_callback(void *ctx, wifi_csi_info_t *data)
{
    (void)ctx;

    if (data == NULL || data->buf == NULL || s_csi_queue == NULL) {
        return;
    }

    

    s_csi_frames_received++;
    s_last_rssi = data->rx_ctrl.rssi;

    if ((s_csi_frames_received % VSENSE_RAW_SEND_EVERY_N_FRAMES) != 0) {
        return;
    }

    vsense_csi_frame_t frame = {
        .ts_us = esp_timer_get_time(),
        .frame_count = s_csi_frames_received,
        .rssi = data->rx_ctrl.rssi,
        .channel = data->rx_ctrl.channel,
        .len = 0,
    };

    frame.len = (uint16_t)data->len;

    if (frame.len > VSENSE_MAX_CSI_LEN) {
        frame.len = VSENSE_MAX_CSI_LEN;
    }
    memcpy(frame.csi, data->buf, frame.len);

    if (xQueueSend(s_csi_queue, &frame, 0) == pdTRUE) {
        s_csi_frames_queued++;
    } else {
        s_csi_frames_dropped++;
    }

    if ((s_csi_frames_received % 1000) == 0) {
        ESP_LOGI(
            TAG,
            "CSI received=%lu queued=%lu sent=%lu dropped=%lu len=%u rssi=%d",
            (unsigned long)s_csi_frames_received,
            (unsigned long)s_csi_frames_queued,
            (unsigned long)s_csi_frames_sent,
            (unsigned long)s_csi_frames_dropped,
            frame.len,
            frame.rssi
        );
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
    vsense_rx_collector_init();

    s_csi_queue = xQueueCreate(
        VSENSE_CSI_QUEUE_LENGTH,
        sizeof(vsense_csi_frame_t)
    );

    if (s_csi_queue == NULL) {
        ESP_LOGE(TAG, "Failed to create CSI queue.");
        vTaskDelete(NULL);
        return;
    }

    BaseType_t task_created = xTaskCreate(
        vsense_csi_sender_task,
        "csi_sender",
        6144,
        NULL,
        5,
        NULL
    );

    if (task_created != pdPASS) {
        ESP_LOGE(TAG, "Failed to create raw CSI sender task.");
        vQueueDelete(s_csi_queue);
        s_csi_queue = NULL;
        vTaskDelete(NULL);
        return;
    }


    BaseType_t health_task_created = xTaskCreate(
        vsense_rx_health_task,
        "rx_health",
        3072,
        NULL,
        3,
        NULL
    );

    if (health_task_created != pdPASS) {
        ESP_LOGW(
            TAG,
            "Failed to create RX health telemetry task."
        );
    }

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
        s_udp_packets_received++;

        if ((s_udp_packets_received - last_logged_count) >= 100) {
            ESP_LOGI(
                TAG,
                "RX packets_received=%lu last_payload=\"%s\"",
                (unsigned long)s_udp_packets_received,
                rx_buffer
            );

            last_logged_count = s_udp_packets_received;
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
