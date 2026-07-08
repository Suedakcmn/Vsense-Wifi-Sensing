# VSense Firmware Notes

## Purpose

This firmware skeleton is the first ESP-IDF base for the VSense project.

The current version does not collect real CSI yet. It only creates a clean ESP-IDF project structure with TX/RX role stubs.

## Current structure

- app_main.c: application entry point
- vsense_config.h: temporary compile-time configuration
- role_tx.c: transmitter role placeholder
- role_rx.c: receiver/CSI role placeholder

## Build

From the repository root:

cd firmware
idfpy set-target esp32s3
idfpy build

Expected output:

Project build complete

Expected binary:

firmware/build/vsense_node.bin

## Next firmware steps

1. Add Wi-Fi initialization.
2. Add TX packet sender at around 100 Hz.
3. Add RX CSI callback.
4. Add UDP output to the Mac collector.
5. Later add MQTT support and node health telemetry.

## References to study

Useful reference repository:

- StevenMHernandez/ESP32-CSI-Tool

Useful files to understand:

- active_sta/main/main.cc: station/TX-like behavior
- active_ap/main/main.cc: AP/RX-like behavior
- _components/csi_component.h: CSI callback and CSI metadata
- _components/sockets_component.h: UDP packet sender logic
