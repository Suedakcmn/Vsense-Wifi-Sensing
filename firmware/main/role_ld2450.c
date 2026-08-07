#include "role_ld2450.h"

#include "sdkconfig.h"

#if CONFIG_VSENSE_NODE_ROLE_LD2450

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

#include "driver/uart.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "ld2450_parser.h"
#include "ld2450_json.h"
#include "ld2450_stream.h"
#include "vsense_config.h"
#include "vsense_mqtt.h"
#include "vsense_wifi.h"

static const char *TAG = "VSENSE_LD2450";

typedef struct {
    ld2450_frame_t frame;
    uint64_t ts_us;
    uint32_t frame_seq;
} ld2450_publish_item_t;

typedef struct {
    uint32_t uart_bytes_received;
    uint32_t frames_received;
    uint32_t frames_invalid;
    uint32_t uart_overflow;
    uint32_t uart_frame_errors;
    uint32_t uart_parity_errors;
    uint32_t baud_scan_count;
    uint32_t current_baud;
    uint32_t frames_queued;
    uint32_t queue_dropped;
    uint32_t mqtt_published;
    uint32_t mqtt_failed;
    uint32_t last_target_count;
    uint64_t last_frame_ts_us;
} ld2450_stats_t;

static QueueHandle_t s_uart_event_queue;
static QueueHandle_t s_frame_queue;
static ld2450_stats_t s_stats;
static portMUX_TYPE s_stats_lock = portMUX_INITIALIZER_UNLOCKED;

#if VSENSE_LD2450_UART_AUTO_BAUD
static const uint32_t LD2450_BAUD_SCAN_SEQUENCE[] = {
    VSENSE_LD2450_UART_BAUD,
    256000,
    115200,
    230400,
    460800,
    57600,
    38400,
    19200,
    9600,
};
#endif

static void ld2450_stats_snapshot(ld2450_stats_t *snapshot)
{
    portENTER_CRITICAL(&s_stats_lock);
    *snapshot = s_stats;
    portEXIT_CRITICAL(&s_stats_lock);
}

static void ld2450_uart_task(void *argument)
{
    (void)argument;

    ld2450_stream_t stream;
    ld2450_stream_init(&stream);

    uint8_t read_buffer[VSENSE_LD2450_UART_READ_CHUNK_SIZE];
    uint8_t frame_buffer[LD2450_DATA_FRAME_SIZE];
    uint32_t next_frame_seq = 0;
    uart_event_t event;
    bool first_uart_sample_logged = false;
    bool first_valid_frame_logged = false;

#if VSENSE_LD2450_UART_AUTO_BAUD
    size_t baud_scan_index = 0;
    bool baud_locked = false;
    uint64_t baud_scan_started_us = (uint64_t)esp_timer_get_time();
#endif

    while (true) {
        bool event_received = xQueueReceive(
            s_uart_event_queue,
            &event,
            pdMS_TO_TICKS(100)
        ) == pdTRUE;

        if (event_received && event.type == UART_DATA) {
            size_t remaining = event.size;

            while (remaining > 0) {
                size_t requested = remaining;
                if (requested > sizeof(read_buffer)) {
                    requested = sizeof(read_buffer);
                }

                int bytes_read = uart_read_bytes(
                    (uart_port_t)VSENSE_LD2450_UART_PORT,
                    read_buffer,
                    requested,
                    pdMS_TO_TICKS(100)
                );

                if (bytes_read <= 0) {
                    break;
                }

                remaining -= (size_t)bytes_read;

                portENTER_CRITICAL(&s_stats_lock);
                s_stats.uart_bytes_received += (uint32_t)bytes_read;
                portEXIT_CRITICAL(&s_stats_lock);

                if (!first_uart_sample_logged) {
                    size_t sample_length = (size_t)bytes_read;
                    if (sample_length > 64) {
                        sample_length = 64;
                    }

                    ESP_LOGI(
                        TAG,
                        "First UART bytes (look for AA FF 03 00 ... 55 CC):"
                    );
                    ESP_LOG_BUFFER_HEXDUMP(
                        TAG,
                        read_buffer,
                        sample_length,
                        ESP_LOG_INFO
                    );
                    first_uart_sample_logged = true;
                }

                for (int index = 0; index < bytes_read; index++) {
                    if (!ld2450_stream_push_byte(
                            &stream,
                            read_buffer[index],
                            frame_buffer
                        )) {
                        continue;
                    }

                    ld2450_publish_item_t item = {0};
                    ld2450_parse_result_t parse_result = ld2450_parse_frame(
                        frame_buffer,
                        sizeof(frame_buffer),
                        &item.frame
                    );

                    portENTER_CRITICAL(&s_stats_lock);
                    s_stats.frames_received++;
                    if (parse_result != LD2450_PARSE_OK) {
                        s_stats.frames_invalid++;
                    }
                    portEXIT_CRITICAL(&s_stats_lock);

                    if (parse_result != LD2450_PARSE_OK) {
                        continue;
                    }

                    if (!first_valid_frame_logged) {
                        ESP_LOGI(TAG, "First valid 30-byte LD2450 frame:");
                        ESP_LOG_BUFFER_HEXDUMP(
                            TAG,
                            frame_buffer,
                            sizeof(frame_buffer),
                            ESP_LOG_INFO
                        );
                        first_valid_frame_logged = true;
                    }

#if VSENSE_LD2450_UART_AUTO_BAUD
                    if (!baud_locked) {
                        baud_locked = true;
                        ESP_LOGI(
                            TAG,
                            "Valid LD2450 frame detected; baud locked at %lu.",
                            (unsigned long)s_stats.current_baud
                        );
                    }
#endif

                    item.ts_us = (uint64_t)esp_timer_get_time();
                    item.frame_seq = next_frame_seq++;

                    if (xQueueSend(s_frame_queue, &item, 0) == pdTRUE) {
                        portENTER_CRITICAL(&s_stats_lock);
                        s_stats.frames_queued++;
                        s_stats.last_target_count = item.frame.target_count;
                        s_stats.last_frame_ts_us = item.ts_us;
                        portEXIT_CRITICAL(&s_stats_lock);
                    } else {
                        portENTER_CRITICAL(&s_stats_lock);
                        s_stats.queue_dropped++;
                        portEXIT_CRITICAL(&s_stats_lock);
                    }
                }
            }
        } else if (event_received && (
            event.type == UART_FIFO_OVF ||
            event.type == UART_BUFFER_FULL
        )) {
            uart_flush_input((uart_port_t)VSENSE_LD2450_UART_PORT);
            xQueueReset(s_uart_event_queue);
            ld2450_stream_init(&stream);

            portENTER_CRITICAL(&s_stats_lock);
            s_stats.uart_overflow++;
            portEXIT_CRITICAL(&s_stats_lock);

            ESP_LOGW(TAG, "UART overflow; input and stream state reset.");
        } else if (event_received && event.type == UART_FRAME_ERR) {
            portENTER_CRITICAL(&s_stats_lock);
            s_stats.uart_frame_errors++;
            portEXIT_CRITICAL(&s_stats_lock);
        } else if (event_received && event.type == UART_PARITY_ERR) {
            portENTER_CRITICAL(&s_stats_lock);
            s_stats.uart_parity_errors++;
            portEXIT_CRITICAL(&s_stats_lock);
        }

#if VSENSE_LD2450_UART_AUTO_BAUD
        uint64_t now_us = (uint64_t)esp_timer_get_time();
        if (
            !baud_locked &&
            now_us - baud_scan_started_us >=
                (uint64_t)VSENSE_LD2450_UART_BAUD_SCAN_INTERVAL_MS * 1000ULL
        ) {
            uint32_t previous_baud;
            uint32_t next_baud;

            portENTER_CRITICAL(&s_stats_lock);
            previous_baud = s_stats.current_baud;
            portEXIT_CRITICAL(&s_stats_lock);

            do {
                baud_scan_index = (baud_scan_index + 1) %
                    (sizeof(LD2450_BAUD_SCAN_SEQUENCE) /
                     sizeof(LD2450_BAUD_SCAN_SEQUENCE[0]));
                next_baud = LD2450_BAUD_SCAN_SEQUENCE[baud_scan_index];
            } while (next_baud == previous_baud);

            uart_flush_input((uart_port_t)VSENSE_LD2450_UART_PORT);
            xQueueReset(s_uart_event_queue);
            ld2450_stream_init(&stream);

            esp_err_t baud_result = uart_set_baudrate(
                (uart_port_t)VSENSE_LD2450_UART_PORT,
                next_baud
            );

            if (baud_result == ESP_OK) {
                portENTER_CRITICAL(&s_stats_lock);
                s_stats.current_baud = next_baud;
                s_stats.baud_scan_count++;
                portEXIT_CRITICAL(&s_stats_lock);

                ESP_LOGW(
                    TAG,
                    "No valid frame at %lu baud; listening at %lu baud.",
                    (unsigned long)previous_baud,
                    (unsigned long)next_baud
                );
            } else {
                ESP_LOGE(
                    TAG,
                    "Failed to switch UART baud to %lu: %s",
                    (unsigned long)next_baud,
                    esp_err_to_name(baud_result)
                );
            }

            baud_scan_started_us = now_us;
        }
#endif
    }
}

static void ld2450_mqtt_task(void *argument)
{
    (void)argument;

    ld2450_publish_item_t item;
    char payload[768];

    while (true) {
        if (xQueueReceive(s_frame_queue, &item, portMAX_DELAY) != pdTRUE) {
            continue;
        }

        size_t payload_length = 0;
        bool formatted = ld2450_format_ground_truth_json(
            VSENSE_NODE_ID,
            item.ts_us,
            item.frame_seq,
            &item.frame,
            payload,
            sizeof(payload),
            &payload_length
        );

        bool published = formatted && vsense_mqtt_publish_message(
            VSENSE_LD2450_GROUND_TRUTH_TOPIC,
            payload,
            payload_length,
            0,
            false
        );

        portENTER_CRITICAL(&s_stats_lock);
        if (published) {
            s_stats.mqtt_published++;
        } else {
            s_stats.mqtt_failed++;
        }
        portEXIT_CRITICAL(&s_stats_lock);
    }
}

static void ld2450_health_task(void *argument)
{
    (void)argument;

    char topic[64];
    int topic_length = snprintf(
        topic,
        sizeof(topic),
        "vsense/%s/health",
        VSENSE_NODE_ID
    );

    if (topic_length < 0 || topic_length >= (int)sizeof(topic)) {
        ESP_LOGE(TAG, "Radar health topic is too long.");
        vTaskDelete(NULL);
        return;
    }

    while (true) {
        vTaskDelay(pdMS_TO_TICKS(VSENSE_HEALTH_INTERVAL_MS));

        ld2450_stats_t stats;
        ld2450_stats_snapshot(&stats);

        uint64_t now_us = (uint64_t)esp_timer_get_time();
        uint64_t last_frame_age_ms = stats.last_frame_ts_us == 0
            ? 0
            : (now_us - stats.last_frame_ts_us) / 1000ULL;

        char payload[768];
        int payload_length = snprintf(
            payload,
            sizeof(payload),
            "{"
            "\"node_id\":\"%s\","
            "\"uptime_ms\":%llu,"
            "\"free_heap\":%lu,"
            "\"minimum_free_heap\":%lu,"
            "\"uart_bytes_received\":%lu,"
            "\"frames_received\":%lu,"
            "\"frames_invalid\":%lu,"
            "\"uart_overflow\":%lu,"
            "\"uart_frame_errors\":%lu,"
            "\"uart_parity_errors\":%lu,"
            "\"current_baud\":%lu,"
            "\"baud_scan_count\":%lu,"
            "\"frames_queued\":%lu,"
            "\"queue_dropped\":%lu,"
            "\"mqtt_published\":%lu,"
            "\"mqtt_failed\":%lu,"
            "\"queue_depth\":%u,"
            "\"last_target_count\":%lu,"
            "\"last_frame_age_ms\":%llu"
            "}",
            VSENSE_NODE_ID,
            (unsigned long long)(now_us / 1000ULL),
            (unsigned long)esp_get_free_heap_size(),
            (unsigned long)esp_get_minimum_free_heap_size(),
            (unsigned long)stats.uart_bytes_received,
            (unsigned long)stats.frames_received,
            (unsigned long)stats.frames_invalid,
            (unsigned long)stats.uart_overflow,
            (unsigned long)stats.uart_frame_errors,
            (unsigned long)stats.uart_parity_errors,
            (unsigned long)stats.current_baud,
            (unsigned long)stats.baud_scan_count,
            (unsigned long)stats.frames_queued,
            (unsigned long)stats.queue_dropped,
            (unsigned long)stats.mqtt_published,
            (unsigned long)stats.mqtt_failed,
            (unsigned int)uxQueueMessagesWaiting(s_frame_queue),
            (unsigned long)stats.last_target_count,
            (unsigned long long)last_frame_age_ms
        );

        if (
            payload_length < 0 ||
            payload_length >= (int)sizeof(payload)
        ) {
            ESP_LOGE(TAG, "Radar health payload is too long.");
            continue;
        }

        (void)vsense_mqtt_publish_message(
            topic,
            payload,
            (size_t)payload_length,
            0,
            false
        );

        ESP_LOGI(
            TAG,
            "HEALTH bytes=%lu frames=%lu invalid=%lu overflow=%lu "
            "frame_err=%lu parity_err=%lu baud=%lu scans=%lu "
            "published=%lu failed=%lu dropped=%lu targets=%lu age_ms=%llu",
            (unsigned long)stats.uart_bytes_received,
            (unsigned long)stats.frames_received,
            (unsigned long)stats.frames_invalid,
            (unsigned long)stats.uart_overflow,
            (unsigned long)stats.uart_frame_errors,
            (unsigned long)stats.uart_parity_errors,
            (unsigned long)stats.current_baud,
            (unsigned long)stats.baud_scan_count,
            (unsigned long)stats.mqtt_published,
            (unsigned long)stats.mqtt_failed,
            (unsigned long)stats.queue_dropped,
            (unsigned long)stats.last_target_count,
            (unsigned long long)last_frame_age_ms
        );

        if (stats.uart_bytes_received == 0) {
            ESP_LOGW(
                TAG,
                "No electrical UART activity on GPIO%d. Verify 5 V at the "
                "radar, common GND, and radar TX -> ESP RX wiring.",
                VSENSE_LD2450_UART_RX_GPIO
            );
        } else if (stats.frames_received == stats.frames_invalid) {
            ESP_LOGW(
                TAG,
                "UART activity exists but no valid LD2450 frame was found. "
                "Likely causes: changed baud rate, noise, or wrong TX source."
            );
        }
    }
}

void vsense_role_ld2450_start(void)
{
    ESP_LOGI(TAG, "LD2450 radar bridge selected.");
    ESP_LOGI(
        TAG,
        "UART=%d baud=%d RX_GPIO=%d TX_GPIO=%d topic=%s",
        VSENSE_LD2450_UART_PORT,
        VSENSE_LD2450_UART_BAUD,
        VSENSE_LD2450_UART_RX_GPIO,
        VSENSE_LD2450_UART_TX_GPIO,
        VSENSE_LD2450_GROUND_TRUTH_TOPIC
    );

    s_frame_queue = xQueueCreate(
        VSENSE_LD2450_FRAME_QUEUE_SIZE,
        sizeof(ld2450_publish_item_t)
    );
    if (s_frame_queue == NULL) {
        ESP_LOGE(TAG, "Failed to create radar frame queue.");
        return;
    }

    const uart_config_t uart_config = {
        .baud_rate = VSENSE_LD2450_UART_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    ESP_ERROR_CHECK(uart_param_config(
        (uart_port_t)VSENSE_LD2450_UART_PORT,
        &uart_config
    ));
    ESP_ERROR_CHECK(uart_set_pin(
        (uart_port_t)VSENSE_LD2450_UART_PORT,
        VSENSE_LD2450_UART_TX_GPIO,
        VSENSE_LD2450_UART_RX_GPIO,
        UART_PIN_NO_CHANGE,
        UART_PIN_NO_CHANGE
    ));
    ESP_ERROR_CHECK(uart_driver_install(
        (uart_port_t)VSENSE_LD2450_UART_PORT,
        VSENSE_LD2450_UART_RX_BUFFER_SIZE,
        0,
        VSENSE_LD2450_UART_EVENT_QUEUE_SIZE,
        &s_uart_event_queue,
        0
    ));

    portENTER_CRITICAL(&s_stats_lock);
    s_stats.current_baud = VSENSE_LD2450_UART_BAUD;
    portEXIT_CRITICAL(&s_stats_lock);

    BaseType_t uart_created = xTaskCreate(
        ld2450_uart_task,
        "ld2450_uart",
        VSENSE_LD2450_TASK_STACK_SIZE,
        NULL,
        VSENSE_LD2450_TASK_PRIORITY,
        NULL
    );
    BaseType_t mqtt_created = xTaskCreate(
        ld2450_mqtt_task,
        "ld2450_mqtt",
        VSENSE_LD2450_TASK_STACK_SIZE,
        NULL,
        VSENSE_LD2450_TASK_PRIORITY,
        NULL
    );
    BaseType_t health_created = xTaskCreate(
        ld2450_health_task,
        "ld2450_health",
        VSENSE_LD2450_TASK_STACK_SIZE,
        NULL,
        VSENSE_LD2450_TASK_PRIORITY,
        NULL
    );

    if (
        uart_created != pdPASS ||
        mqtt_created != pdPASS ||
        health_created != pdPASS
    ) {
        ESP_LOGE(TAG, "Failed to create one or more radar tasks.");
        return;
    }

    ESP_LOGI(TAG, "LD2450 UART, publish, and health tasks started.");

    /*
     * UART must be live before this blocking Wi-Fi call. Otherwise a missing
     * access point prevents the radar input from ever being initialized.
     */
    vsense_wifi_connect_sta();
    vsense_mqtt_start();
}

#else

void vsense_role_ld2450_start(void)
{
}

#endif
