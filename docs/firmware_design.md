# VSense Firmware Design

## Purpose

This document describes the planned firmware architecture for VSense ESP32-S3 nodes.

The current firmware only contains a buildable skeleton. Future PRs will add Wi-Fi initialization, TX packet sending, RX CSI collection, UDP output, MQTT support, and node health telemetry.

## Current Status

The firmware currently includes:

- ESP-IDF project structure
- app_main.c entry point
- vsense_config.h temporary configuration file
- TX role stub
- RX role stub
- ESP32-S3 build support

The current firmware does not collect real CSI yet.

## Node Roles

VSense nodes can run in two main roles:

- TX: transmitter node
- RX: receiver / CSI collection node

The role is currently selected through VSENSE_NODE_ROLE in vsense_config.h.

## TX Role

The TX node will generate Wi-Fi traffic so RX nodes can extract CSI.

Planned TX responsibilities:

1. Initialize Wi-Fi.
2. Use the configured Wi-Fi channel.
3. Send packets at around VSENSE_PACKET_RATE_HZ.
4. Prefer unicast transmission when RX address or IP is known.
5. Track packet count.
6. Report basic health information.

Target behavior:

- Packet rate: around 100 Hz
- Purpose: create stable Wi-Fi traffic for CSI measurements
- Future config: target RX IP / MAC / channel / packet rate

## RX Role

The RX node will collect CSI from received Wi-Fi frames.

Planned RX responsibilities:

1. Initialize Wi-Fi.
2. Configure the Wi-Fi channel.
3. Enable CSI collection.
4. Register a CSI callback.
5. Extract metadata from each CSI frame:
   - timestamp
   - RSSI
   - channel
   - source MAC
   - CSI length
   - raw CSI buffer
6. Forward CSI frames to the Mac collector.
7. Later support MQTT publishing.

## CSI Callback

The CSI callback is the function that will run automatically whenever a new CSI frame is available.

Expected callback flow:

1. ESP-IDF receives a Wi-Fi frame.
2. CSI data becomes available.
3. Registered CSI callback is called.
4. Firmware extracts metadata and raw CSI bytes.
5. Firmware packages the data.
6. Firmware sends the packet to the collector.

## Transport Plan

### Version 0: UDP

The first real hardware version should use UDP because it is simple and fast.

Planned flow:

RX ESP32-S3 -> UDP packet -> Mac collector

### Future: MQTT

Later, firmware may publish CSI and health data to MQTT topics:

- vsense/{node_id}/csi
- vsense/{node_id}/health

## Health Telemetry

Each node should eventually report health information.

Possible health fields:

- node_id
- role
- uptime
- free heap
- Wi-Fi status
- packet_count
- csi_packet_count
- csi_pps
- firmware version

## Next Firmware Implementation Steps

1. Add common Wi-Fi initialization helpers.
2. Add TX packet sender task.
3. Add RX CSI initialization.
4. Add CSI callback stub.
5. Add UDP packet output.
6. Add health telemetry.
7. Add MQTT support after UDP path is stable.
