# MQTT Smoke Test

This document verifies that Mosquitto can publish and subscribe locally.

## Terminal 1: Start broker

```bash
mosquitto -v

## Terminal 2: Subscribe

```bash
mosquitto_sub -h localhost -t "vsense/rx_01/csi"
```

## Terminal 3: Publish test message

```bash
mosquitto_pub -h localhost -t "vsense/rx_01/csi" -m '{"ts_us":0,"node_id":"rx_01","rssi":-55,"csi":[3,4,-2,5],"label":"empty"}'
```

Expected result: the message should appear in Terminal 2.