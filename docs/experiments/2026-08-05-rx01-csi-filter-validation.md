# RX-01 CSI Source Filter Validation — 5 August 2026

## Purpose

Determine whether mixed CSI vector lengths and large RSSI jumps come from
unrelated Wi-Fi traffic entering the RX sensing path, then validate the TX MAC
filter on RX-01 before changing RX-02.

## Verified Setup

- TX-01 station MAC: `84:fc:e6:5e:50:24`
- RX-01 station MAC: `28:84:85:46:49:10`
- access-point BSSID: `06:e2:c6:ea:22:fa`
- Wi-Fi channel: 1, BW20
- TX target rate: 100 packets/s
- forwarding interval: every accepted frame (`N=1`)

Environment credentials remain only in ignored generated build configuration
and are not recorded in this document.

## Filter-Disabled Baseline

RX-01 reported CSI callbacks from TX-01, the access point, and another nearby
Wi-Fi source. The callback RSSI moved between approximately -10 dBm, -50 dBm,
and -80 dBm even though the cards remained stationary.

A 500-message raw MQTT sample produced:

| Metric | Result |
| --- | ---: |
| 128-byte CSI | 9 (1.8%) |
| 256-byte CSI | 491 (98.2%) |
| RSSI range | -80 to -10 dBm |

Firmware transport remained healthy: no queue drops, oversized frames, or
steady-state UDP/MQTT failures were observed. The failure was source selection,
not transport capacity.

## TX MAC Filter Canary

RX-01 was backed up before the canary. The filter was enabled with the verified
TX-01 MAC; RX-02 was left unchanged. The canary connected to Wi-Fi/MQTT and
continued accepting approximately 81–87 CSI frames/s with zero queue drops.
Access-point callbacks were counted and rejected by the MAC filter.

A 2,000-message filtered MQTT sample produced:

| Metric | Result |
| --- | ---: |
| 128-byte CSI | 2 (0.1%) |
| 256-byte CSI | 1,998 (99.9%) |
| RSSI range | -12 to -9 dBm |

## Decision

The TX MAC filter materially removes unrelated traffic and is retained for
controlled RX profiles. The remaining 128-byte frames pass the verified TX MAC
filter, so they must not be hidden with padding or truncation. Add a separate,
configurable expected-length filter at 256 bytes, expose its own health counter,
and validate it on RX-01 before updating RX-02.

## Expected-Length Filter Canary

The configurable expected-length filter was enabled at 256 raw bytes on RX-01.
Only the application partition was updated; RX-02 was not flashed. RX-01
reconnected to the locked access point and MQTT broker, and both source and
length filters were reported as enabled at startup.

A 2,000-message MQTT sample after the change produced:

| Metric | Result |
| --- | ---: |
| 256-byte `.len` | 2,000 (100%) |
| 256-value CSI array | 2,000 (100%) |
| RSSI range | -32 to -29 dBm |

The health sample observed during the canary reported 94 length-filtered
frames, 7,779 received and sent frames, zero queue drops, zero oversized
frames, and zero UDP/MQTT CSI failures. This confirms that the occasional
128-byte frames still arrive from the verified TX source but are rejected
before entering the queue or transport path.

## Outcome

The two independent filters now have distinct responsibilities and telemetry:

- the TX MAC filter rejects CSI from unrelated Wi-Fi sources;
- the expected-length filter rejects structurally incompatible CSI frames;
- neither filter pads, truncates, or rewrites accepted CSI data.

Keep the global defaults disabled so new environments must opt in after
measuring their source MAC and CSI length. RX-01 may use both verified filter
values. RX-02 keeps the length filter disabled until an equivalent physical
canary confirms its own length distribution and transport health.

## Plotter Soak Check

The canonical `mqtt_collector.py | csi_live_plot.py` pipeline was restricted to
RX-01 topics and observed for more than five minutes. The plotter detected only
`rx_01` and produced none of the following diagnostics:

- `CSI vector length changed`;
- `Resetting its score buffer`;
- selected-subcarrier index errors;
- invalid JSON/CSI errors;
- offline transitions.

This validates the fixed-length contract at the plotter boundary. During the
longer device uptime, health telemetry also exposed a separate transient queue
backlog: cumulative drop and earlier MQTT-failure counters were non-zero. One
6.84-second interval added 84 queue drops while MQTT failures stayed unchanged;
the following two five-second intervals accepted all 800 frames with zero new
drops or MQTT failures and returned to a queue depth of 0–4. Do not attribute
this transient transport backlog to the length filter or plotter without a
controlled before/after soak test.

## MQTT Backpressure Follow-up

A later plotter-disabled baseline and a clean RX-01 reboot reproduced queue
backpressure independently of the length filter: the clean boot accumulated 60
queue drops within approximately 17 seconds while UDP failures remained zero.
The CSI sender used blocking `esp_mqtt_client_publish()` for MQTT immediately
after UDP delivery, so an MQTT network stall could delay the shared sender loop.

The controlled follow-up changes only CSI MQTT submission to the non-blocking
ESP-MQTT outbox API. The outbox is bounded at 32 KiB, its worker priority is
above the CSI sender, and health telemetry exposes outbox-full rejects and
current byte usage. This remains a canary until a fresh RX-01 application build
is flashed and both plotter-disabled and plotter-enabled soak tests pass.

## Final RX-01 Filter Soak

The already-flashed RX-01 filter build was observed for approximately 10.7
minutes without changing firmware or broker configuration. A streaming sample
of 50,000 MQTT CSI messages produced:

| Metric | Result |
| --- | ---: |
| Wrong node ID | 0 |
| `.len` values other than 256 | 0 |
| CSI arrays other than 256 values | 0 |
| `.len`/array-length mismatches | 0 |
| RSSI range | -60 to -29 dBm |

Across the same interval, `csi_dropped` remained at 60,
`mqtt_csi_failed` remained at 2, `udp_csi_failed` remained at 0,
`csi_oversized` remained at 0, and the queue returned to depth 0. These are
cumulative boot counters; none of the transport error counters increased
during this soak. Free heap changed from 180,480 to 179,668 bytes.

This completes the RX-01 source/shape-filter canary. It does not validate the
unflashed MQTT outbox follow-up or RX-02 hardware.
