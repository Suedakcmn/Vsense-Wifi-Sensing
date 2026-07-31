# Multi-RX N=1 Validation — 31 July 2026

## Purpose

Validate the firmware-hardening changes with TX-01, RX-01, and RX-02 running
simultaneously. The run checks full forwarding (`N=1`), queue stability,
transport stability, oversized-frame handling, and per-node continuity before
the LD2450 integration.

## Setup

- Wi-Fi: `ValensasSetup`, channel 1
- Collector: `192.168.128.167:4444`
- MQTT broker: `mqtt://192.168.128.167`
- TX-01 MAC: `84:fc:e6:5e:50:24`
- RX-01 MAC: `28:84:85:46:49:10`, IP `192.168.128.31`
- RX-02 MAC: `e0:72:a1:f3:bf:f0`, IP `192.168.128.168`
- TX target rate: 100 packets/s per RX
- CSI forwarding: every accepted frame (`N=1`)
- CSI maximum length: 384 bytes
- CSI queue: 128 entries
- Queue enqueue timeout: 5 ms in the UDP probe task
- Sender task priority: 6

The RX nodes were physically separated for the final run rather than being
placed directly next to each other. The UDP collector, MQTT health subscriber,
and MQTT live plot were active together.

## Final Recorded Run

Local artifact:

```text
data/sessions/20260731_103704_office_rate_verify_r03_csi.jsonl
```

| Metric | RX-01 | RX-02 |
| --- | ---: | ---: |
| Valid CSI packets | 21,384 | 20,779 |
| Device-local duration | 255.655 s | 255.673 s |
| Average recorded rate | 83.644 pps | 81.272 pps |
| Missing frame counts | 0 | 0 |
| Frame counter resets | 0 | 0 |
| 256-byte CSI frames | 21,261 | 20,649 |
| 128-byte CSI frames | 123 | 130 |
| Channel | 1 | 1 |
| RSSI average | -59.89 dBm | -62.45 dBm |
| RSSI range | -79 to -36 dBm | -84 to -29 dBm |

Overall wall-clock duration was 255.623 seconds. The collector accepted 42,163
packets at an aggregate 164.942 pps and reported zero invalid or filtered
packets.

## Health Counter Result

Across the acceptance window:

- `csi_dropped` stayed at 0 on both RX nodes;
- `csi_oversized` stayed at 0 on both RX nodes;
- queue depth returned to 0 on both RX nodes;
- RX-01 UDP/MQTT failure counters stayed at their baseline values of 87/98;
- RX-02 UDP/MQTT failure counters stayed at their baseline values of 0/11;
- minimum observed free heap was 99,876 bytes on RX-01 and 115,356 bytes on
  RX-02.

The transport failure counters are cumulative from boot. Their non-zero
baseline values were produced before all host collectors were ready; neither
counter increased during the recorded acceptance window.

## Packet-Rate Decision

The TX probe counter advances at approximately 100 packets/s per target, but
the final recorded CSI rate was approximately 81–84 pps per RX. This is not
intentional decimation: `raw_send_every_n_frames=1`, accepted and forwarded
rates match, and the saved frame counters have no gaps.

The remaining difference is the measured Wi-Fi/CSI capture yield: not every TX
UDP probe has a fresh CSI callback available when the RX consumes its latest
radio snapshot. Because the full dual-transport run is stable, has no firmware
drops, and preserves every accepted frame, `N=1` remains the selected setting.
The measured rate must be used for LD2450 synchronization planning rather than
claiming an exact 100 CSI samples/s.

## Additional Acceptance Checks

- Offline watchdog: disconnecting RX-02 produced
  `status=offline, source=timeout`; reconnecting it restored `status=online`
  while RX-01 stayed online.
- Wrong-MAC test: with the filter temporarily enabled and
  `00:11:22:33:44:55` configured, `csi_filtered` rose to 8,062,
  `csi_received` stayed at 0, and rate-limited `TX MAC mismatch` warnings were
  printed. RX-02 was then restored to the normal profile with the filter
  disabled and the verified TX MAC retained in configuration.

## Decision

The multi-RX `N=1` firmware path is accepted for the next integration step.
The approximately 81–84 pps hardware result is a documented limitation, not a
configured reduction. LD2450 validation must measure synchronization against
the collector timestamp and the observed rate.
