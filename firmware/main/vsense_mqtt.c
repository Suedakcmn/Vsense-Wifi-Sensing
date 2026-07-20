#include "vsense_mqtt.h"

#include <stdbool.h>
#include <stdio.h>

#include "esp_event.h"
#include "esp_log.h"
#include "mqtt_client.h"

#include "vsense_config.h"

static const char *TAG = "VSENSE_MQTT";

static esp_mqtt_client_handle_t s_mqtt_client = NULL;
static bool s_mqtt_connected = false;

static void vsense_mqtt_event_handler(
    void *handler_args,
    esp_event_base_t base,
    int32_t event_id,
    void *event_data
)
{
    (void)handler_args;
    (void)base;
    (void)event_data;

    switch ((esp_mqtt_event_id_t)event_id) {
        case MQTT_EVENT_CONNECTED:
            s_mqtt_connected = true;
            ESP_LOGI(
                TAG,
                "Connected to MQTT broker: %s",
                VSENSE_MQTT_BROKER_URI
            );
            break;

        case MQTT_EVENT_DISCONNECTED:
            s_mqtt_connected = false;
            ESP_LOGW(TAG, "Disconnected from MQTT broker.");
            break;

        case MQTT_EVENT_ERROR:
            s_mqtt_connected = false;
            ESP_LOGE(TAG, "MQTT client error.");
            break;

        default:
            break;
    }
}

void vsense_mqtt_start(void)
{
    if (s_mqtt_client != NULL) {
        ESP_LOGW(TAG, "MQTT client already started.");
        return;
    }

    const esp_mqtt_client_config_t mqtt_config = {
        .broker.address.uri = VSENSE_MQTT_BROKER_URI,
        .buffer.size = 2048,
        .buffer.out_size = 4096,
    };

    s_mqtt_client = esp_mqtt_client_init(
        &mqtt_config
    );

    if (s_mqtt_client == NULL) {
        ESP_LOGE(TAG, "Failed to initialize MQTT client.");
        return;
    }

    esp_err_t err = esp_mqtt_client_register_event(
        s_mqtt_client,
        ESP_EVENT_ANY_ID,
        vsense_mqtt_event_handler,
        NULL
    );

    if (err != ESP_OK) {
        ESP_LOGE(
            TAG,
            "Failed to register MQTT event handler: %s",
            esp_err_to_name(err)
        );
        esp_mqtt_client_destroy(s_mqtt_client);
        s_mqtt_client = NULL;
        return;
    }

    err = esp_mqtt_client_start(s_mqtt_client);

    if (err != ESP_OK) {
        ESP_LOGE(
            TAG,
            "Failed to start MQTT client: %s",
            esp_err_to_name(err)
        );
        esp_mqtt_client_destroy(s_mqtt_client);
        s_mqtt_client = NULL;
        return;
    }

    ESP_LOGI(
        TAG,
        "MQTT client started. Broker=%s",
        VSENSE_MQTT_BROKER_URI
    );
}

bool vsense_mqtt_is_connected(void)
{
    return s_mqtt_connected;
}

bool vsense_mqtt_publish_health(
    uint64_t uptime_ms,
    uint32_t free_heap,
    uint32_t minimum_free_heap,
    uint32_t udp_packets,
    uint32_t csi_received,
    uint32_t csi_queued,
    uint32_t csi_sent,
    uint32_t udp_csi_sent,
    uint32_t udp_csi_failed,
    uint32_t mqtt_csi_published,
    uint32_t mqtt_csi_failed,
    uint32_t csi_dropped,
    uint32_t queue_depth,
    int8_t last_rssi
)
{
    if (
        s_mqtt_client == NULL ||
        !s_mqtt_connected
    ) {
        ESP_LOGW(
            TAG,
            "Health telemetry not published: MQTT is disconnected."
        );
        return false;
    }

    char topic[64];

    int topic_length = snprintf(
        topic,
        sizeof(topic),
        "vsense/%s/health",
        VSENSE_NODE_ID
    );

    if (
        topic_length < 0 ||
        topic_length >= (int)sizeof(topic)
    ) {
        ESP_LOGE(TAG, "Health MQTT topic is too long.");
        return false;
    }

    char payload[512];

    int payload_length = snprintf(
        payload,
        sizeof(payload),
        "{"
        "\"node_id\":\"%s\","
        "\"uptime_ms\":%llu,"
        "\"free_heap\":%lu,"
        "\"minimum_free_heap\":%lu,"
        "\"udp_packets\":%lu,"
        "\"csi_received\":%lu,"
        "\"csi_queued\":%lu,"
        "\"csi_sent\":%lu,"
        "\"udp_csi_sent\":%lu,"
        "\"udp_csi_failed\":%lu,"
        "\"mqtt_csi_published\":%lu,"
        "\"mqtt_csi_failed\":%lu,"
        "\"csi_dropped\":%lu,"
        "\"queue_depth\":%lu,"
        "\"last_rssi\":%d"
        "}",
        VSENSE_NODE_ID,
        (unsigned long long)uptime_ms,
        (unsigned long)free_heap,
        (unsigned long)minimum_free_heap,
        (unsigned long)udp_packets,
        (unsigned long)csi_received,
        (unsigned long)csi_queued,
        (unsigned long)csi_sent,
        (unsigned long)udp_csi_sent,
        (unsigned long)udp_csi_failed,
        (unsigned long)mqtt_csi_published,
        (unsigned long)mqtt_csi_failed,
        (unsigned long)csi_dropped,
        (unsigned long)queue_depth,
        (int)last_rssi
    );

    if (
        payload_length < 0 ||
        payload_length >= (int)sizeof(payload)
    ) {
        ESP_LOGE(TAG, "Health MQTT payload is too long.");
        return false;
    }

    int message_id = esp_mqtt_client_publish(
        s_mqtt_client,
        topic,
        payload,
        payload_length,
        0,
        0
    );

    if (message_id < 0) {
        ESP_LOGE(
            TAG,
            "Failed to publish health telemetry."
        );
        return false;
    }

    ESP_LOGI(
        TAG,
        "Health telemetry published. Topic=%s message_id=%d",
        topic,
        message_id
    );

    return true;
}

bool vsense_mqtt_publish_csi(
    const char *payload,
    size_t payload_length
)
{
    if (payload == NULL || payload_length == 0) {
        return false;
    }

    if (
        s_mqtt_client == NULL ||
        !s_mqtt_connected
    ) {
        return false;
    }

    char topic[64];

    int topic_length = snprintf(
        topic,
        sizeof(topic),
        "vsense/%s/csi",
        VSENSE_NODE_ID
    );

    if (
        topic_length < 0 ||
        topic_length >= (int)sizeof(topic)
    ) {
        ESP_LOGE(TAG, "CSI MQTT topic is too long.");
        return false;
    }

    int message_id = esp_mqtt_client_publish(
        s_mqtt_client,
        topic,
        payload,
        (int)payload_length,
        0,
        0
    );

    if (message_id < 0) {
        return false;
    }

    return true;
}
