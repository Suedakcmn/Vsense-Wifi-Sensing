# VSense Firmware Design

## Purpose

This document describes the implemented ESP32-S3 firmware for VSense
multi-node CSI sensing.

## Current architecture

The firmware supports one TX node and one or two RX nodes. Each physical node
uses a separate build directory and Kconfig profile.

```text
TX-01 -- UDP traffic --> RX-01 -- raw CSI --> UDP collector
   \                   RX-01 -- raw CSI --> MQTT broker
    \-> UDP traffic --> RX-02 -- raw CSI --> UDP collector
                       RX-02 -- raw CSI --> MQTT broker
```

UDP and MQTT delivery have independent success/failure counters. They run from
the same CSI sender task, so full-rate tests must verify queue depth and both
transport paths together.

## Configuration

Project settings are declared in `main/Kconfig.projbuild` and exposed through
`main/vsense_config.h`. Important settings include:

- node ID and TX/RX role;
- Wi-Fi SSID, channel, and optional AP BSSID lock;
- TX packet rate and one/two RX target addresses;
- optional expected TX MAC filter;
- collector UDP address and MQTT broker;
- MQTT keepalive and health interval;
- maximum CSI length;
- `VSENSE_RAW_SEND_EVERY_N_FRAMES`.

The TX MAC filter is disabled by default. Controlled production recordings may
enable it after verifying the physical TX station MAC. Filtered frames are
counted and rate-limited mismatch warnings include the last actual source MAC.

Wi-Fi power save is disabled after `esp_wifi_start()` to reduce CSI arrival
jitter.

## TX role

The TX connects as a Wi-Fi station and sends a small unicast UDP payload at
`VSENSE_PACKET_RATE_HZ` to every enabled RX target. Each target has independent
sent and failed counters. The default target rate is 100 Hz.

## RX role and CSI callback

The RX connects to Wi-Fi, starts MQTT, creates the collector UDP socket, then
enables promiscuous mode and CSI collection.

The CSI callback deliberately performs only bounded work:

1. validate the callback data;
2. update source/channel/RSSI diagnostics;
3. apply the optional TX MAC filter;
4. reject and count frames larger than `VSENSE_CSI_BUFFER_MAX_LEN`;
5. copy the latest valid radio measurement into a protected snapshot.

Forwarding CSI over UDP/MQTT also generates local Wi-Fi traffic and therefore
additional CSI callbacks. To prevent that traffic from feeding back into the
forwarding path, each received TX UDP probe consumes at most one fresh snapshot.
The configured forwarding interval is applied to these probe-matched samples.

The queue length is 128. A separate sender task serializes queued CSI as JSON
and attempts both UDP and MQTT delivery. A failure on one transport does not
prevent the other attempt. Because enqueueing happens in the UDP probe task
rather than the radio callback, it may wait for at most 5 ms for the
higher-priority sender to drain a transiently full queue. This keeps the CSI
callback non-blocking while avoiding avoidable burst losses.

## CSI length and transport buffers

`VSENSE_CSI_BUFFER_MAX_LEN` is the single firmware limit and defaults to 384
bytes. The JSON buffer is derived from that value using the maximum text width
of a signed `int8_t`. A compile-time assertion prevents the resulting JSON from
exceeding the 4096-byte MQTT/UDP transport buffers.

Oversized CSI frames are dropped rather than silently truncated. The
`csi_oversized` and `csi_dropped` health counters make this visible.

## Sampling and decimation

`VSENSE_RAW_SEND_EVERY_N_FRAMES` controls intentional decimation:

- `1`: forward every accepted CSI frame;
- `2`: forward every second accepted frame;
- `10`: forward every tenth accepted frame.

The default is 1. Any value greater than 1 must be supported by a recorded
bandwidth/CPU/queue test and a synchronization rationale. The 27 July pilot used
2 and measured roughly 47–55 forwarded frames/s.

The 31 July dual-RX validation retained `N=1` for more than four minutes. It
measured 83.644 pps on RX-01 and 81.272 pps on RX-02, with no frame gaps,
firmware drops, oversized frames, or steady-state transport failures. The TX
probe rate remained approximately 100 packets/s per target; the difference is
the measured Wi-Fi/CSI capture yield rather than configured decimation. See
`experiments/2026-07-31-multi-rx-n1-validation.md`.

## Health telemetry

RX health is logged and published to `vsense/{node_id}/health`. It includes:

- cumulative callback, filtered, accepted, queued, sent, dropped, and
  oversized counts;
- UDP and MQTT success/failure counts;
- current queue depth and heap diagnostics;
- `csi_pps`, the accepted CSI rate during the latest health interval;
- `csi_forwarded_pps`, the queue input rate after intentional decimation;
- configured forwarding interval and latest RSSI.

Node status is retained at `vsense/{node_id}/status`. Firmware MQTT keepalive
defaults to 30 seconds. The platform collector independently marks a node
offline after five seconds without CSI, health, or status traffic.

## Timestamps and synchronization

Firmware `ts_us` comes from `esp_timer_get_time()` and is device uptime. It is
not directly comparable between RX nodes or with an LD2450 connected to the
Mac.

Both MQTT and UDP collectors add:

- `recorded_at`: UTC receive time;
- `collector_ts_us`: Unix epoch receive time in microseconds.

Use `collector_ts_us` as the initial common timebase for multi-RX/radar
alignment. Keep firmware `ts_us` for device-local interval and jitter analysis.
Network and serial latency still need to be measured during LD2450 validation.

## Required hardware verification

Before accepting a firmware profile:

1. verify node ID, role, addresses, Wi-Fi channel, and physical TX MAC;
2. run both RX nodes simultaneously for at least two to three minutes;
3. confirm accepted and forwarded rates match the configured expectations;
4. confirm frame-count step is 1 at the default forwarding interval;
5. confirm queue depth recovers, drop/oversize counters stay zero, and
   transport failure counters do not increase after the collector and broker
   baseline is captured;
6. test MAC filter disabled, incorrect, and correct configurations;
7. disconnect one RX and confirm only that node becomes offline;
8. save the recording under the canonical session naming standard.
