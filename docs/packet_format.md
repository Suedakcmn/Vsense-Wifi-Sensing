# VSense CSI Packet Format

## Purpose

This document defines the implemented JSON contract between RX ESP32-S3 nodes
and the Mac collector. `csi_replay.py` can simulate the same logical shape.

## Firmware CSI JSON

The RX firmware sends one JSON object per CSI frame with:

- ts_us
- node_id
- frame_count
- rssi
- channel
- len
- csi

Example:

```json
{"ts_us":123456,"node_id":"rx_01","frame_count":42,"rssi":-55,"channel":6,"len":4,"csi":[3,4,-2,5]}
```

`ts_us` is device uptime from the RX and `frame_count` counts accepted CSI
frames before intentional decimation. `len` must equal the number of entries in
`csi`.

Collectors add `recorded_at` and `collector_ts_us`. The latter is the common
Mac clock for multi-RX and LD2450 alignment.

This format is useful for replay/live testing before real ESP32 hardware is available.

## Important Note About Label

label is not expected from ESP32 firmware.

It may exist only in recorded datasets for analysis, validation, or ML experiments.

Real RX firmware should send CSI and metadata, not activity labels.

## CSI Payload Layout

The CSI payload is expected to contain raw signed 8-bit values.

Expected layout:

[imag0, real0, imag1, real1, imag2, real2, ...]

Amplitude for each subcarrier can be computed as:

amplitude = sqrt(real^2 + imag^2)

Phase can be computed as:

phase = atan2(imag, real)

## Transports

The same CSI JSON payload is attempted independently over:

- RX ESP32-S3 -> UDP -> Mac collector
- RX ESP32-S3 -> MQTT broker -> Mac collector

Configuration is defined through Kconfig and exposed by `vsense_config.h`.
MQTT topics are:

- `vsense/{node_id}/csi`
- `vsense/{node_id}/health`
- `vsense/{node_id}/status`

## Open Questions

1. When should JSON be replaced by a compact binary representation?
2. Is collector receive time sufficiently accurate for LD2450 alignment, or
   is clock/latency calibration required?
3. Should accepted source MAC be included in every recorded CSI row?
4. Is an application checksum needed in addition to UDP/Wi-Fi integrity?
