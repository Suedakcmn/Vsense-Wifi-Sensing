# VSense CSI Packet Format v0

## Purpose

This document defines the first proposed packet contract between RX ESP32-S3 nodes and the Mac collector.

During Week 1, hardware is not available. Therefore, csi_replay.py can simulate a similar packet shape using the provided CSI dataset.

When hardware arrives, RX firmware should produce packets compatible with this structure.

## Current Server-Side Logical Format

The current server skeleton expects JSON-line messages with fields similar to:

- ts_us
- node_id
- rssi
- csi
- label

Example logical message:

{
  "ts_us": 0,
  "node_id": "rx_01",
  "rssi": -55,
  "csi": [3, 4, -2, 5],
  "label": "empty"
}

This format is useful for replay/live testing before real ESP32 hardware is available.

## Important Note About Label

label is not expected from ESP32 firmware.

It may exist only in recorded datasets for analysis, validation, or ML experiments.

Real RX firmware should send CSI and metadata, not activity labels.

## Proposed Firmware Packet Fields

- magic: constant marker to identify VSense packets
- version: packet format version
- node_id: RX node identifier
- seq_no: increasing packet sequence number
- ts_us: timestamp in microseconds
- rssi: received signal strength
- channel: Wi-Fi channel
- csi_len: number of CSI bytes
- csi_payload: raw CSI values in imag/real pairs

## CSI Payload Layout

The CSI payload is expected to contain raw signed 8-bit values.

Expected layout:

[imag0, real0, imag1, real1, imag2, real2, ...]

Amplitude for each subcarrier can be computed as:

amplitude = sqrt(real^2 + imag^2)

Phase can be computed as:

phase = atan2(imag, real)

## Transport v0

Version 0 transport:

RX ESP32-S3 -> UDP -> Mac collector

Default collector settings are currently stored in vsense_config.h:

- VSENSE_COLLECTOR_IP
- VSENSE_COLLECTOR_UDP_PORT

## Future MQTT Topics

Future CSI topic:

vsense/{node_id}/csi

Future health topic:

vsense/{node_id}/health

## Open Questions

1. Should node_id be fixed-length bytes or a string?
2. Should we include source MAC address?
3. Should timestamp come from ESP32 or Mac collector?
4. Should CSI payload be sent raw or compressed?
5. Should UDP packets include a checksum?
6. Should RSSI and channel be included in every packet?
7. Should the first hardware version use JSON for debugging or compact binary for performance?
