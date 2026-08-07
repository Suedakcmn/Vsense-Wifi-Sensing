# LD2450 and RX1 synchronized validation — 2026-08-07

## Purpose

Validate the Week 5 hardware path and record RX1 CSI together with real LD2450
ground truth on the collector's common clock. This run replaces the earlier
`bytes=0` blocked state with measured end-to-end evidence.

## Tested revision and topology

- Firmware revision: `3ce3712`
- Session ID: `20260807_153938_office_walking_r02`
- MQTT broker: `mqtt://192.168.128.167`
- CSI node: `rx_01`
- Radar node: `ld2450_01`
- Radar UART: UART2 at 256000 baud
- Radar TX to S3 GPIO18; radar RX to S3 GPIO17
- Radar 5 V and GND supplied by an ESP32-C5 board
- C5 GND connected to S3 GND; C5 and S3 5 V rails not connected
- ESP32-S3 retained the UART, Wi-Fi, parser, and MQTT bridge roles

The C5 was a power source only. The Mac was kept awake with `caffeinate` for
the complete run. Large session files must remain local and must not be added
to Git. The preserved local copy is under
`data/sessions/week5/20260807_153938_office_walking_r02/`.

## Procedure

The canonical MQTT collector subscribed to binary CSI, radar ground truth,
health, and status topics. It wrote separate CSI, ground-truth, and telemetry
JSONL files under one session ID. The scenario included an initial still
period, walking inside the radar field, and a final still period.

```bash
caffeinate -dimsu \
python server/mqtt_collector.py \
  --host 127.0.0.1 \
  --port 1883 \
  --client-id vsense-week5-r02 \
  --session-dir data/sessions/20260807_153938_office_walking_r02 \
  --session-id 20260807_153938_office_walking_r02 \
  >/dev/null
```

## Recorded stream results

| Metric | RX1 CSI | LD2450 ground truth |
| --- | ---: | ---: |
| JSONL records | 40,527 | 6,845 |
| Collector duration | 609.222 s | 609.139 s |
| Average recorded rate | 66.521 Hz | 11.236 Hz |
| p99 inter-arrival gap | 122.260 ms | 202.165 ms |
| Maximum inter-arrival gap | 1,299.484 ms | 711.177 ms |

All 47,616 recorded JSONL rows parsed successfully. Only `rx_01` appeared in
the CSI file. The telemetry stream contained 244 rows and no offline
transition during the run.

## Radar frame and target results

| Metric | Result |
| --- | ---: |
| First radar frame sequence | 21,370 |
| Last radar frame sequence | 28,214 |
| Expected unique sequence count | 6,845 |
| Recorded unique sequence count | 6,845 |
| Missing sequences | 0 |
| Duplicate sequences | 0 |
| Frames with at least one target | 4,543 |
| Empty-target frames | 2,302 |
| Maximum simultaneous targets | 2 |
| X range | -1321 mm to 1257 mm |
| Y range | 199 mm to 1593 mm |
| Speed range | -96 cm/s to 152 cm/s |
| Non-zero-speed target observations | 1,317 |

## Health counter deltas

### LD2450 bridge

| Counter | Start | End | Delta |
| --- | ---: | ---: | ---: |
| `uart_bytes_received` | 638,220 | 845,520 | +207,300 |
| `frames_received` | 21,274 | 28,184 | +6,910 |
| `frames_queued` | 21,178 | 28,088 | +6,910 |
| `mqtt_published` | 16,870 | 23,780 | +6,910 |
| `frames_invalid` | 0 | 0 | 0 |
| `uart_overflow` | 0 | 0 | 0 |
| `uart_frame_errors` | 0 | 0 | 0 |
| `uart_parity_errors` | 0 | 0 | 0 |
| `mqtt_failed` | 4,308 | 4,308 | 0 |
| `queue_dropped` | 96 | 96 | 0 |
| Final `queue_depth` | — | 0 | — |

The non-zero cumulative failure and drop values predate this acceptance run.
Neither counter increased during R02.

### RX1

| Counter | Start | End | Delta |
| --- | ---: | ---: | ---: |
| `csi_callbacks` | 277,662 | 422,594 | +144,932 |
| `csi_filtered` | 152,744 | 235,426 | +82,682 |
| `csi_length_filtered` | 1,352 | 2,002 | +650 |
| `csi_received` | 85,366 | 125,808 | +40,442 |
| `csi_queued` | 84,677 | 125,119 | +40,442 |
| `mqtt_csi_published` | 54,648 | 95,089 | +40,441 |
| `mqtt_csi_failed` | 30,029 | 30,029 | 0 |
| `csi_dropped` | 689 | 689 | 0 |
| Final `queue_depth` | — | 0 | — |

The 650 length-filtered callbacks are rejected non-canonical inputs, not drops
from the accepted CSI queue. Accepted CSI drops and MQTT failures did not
increase during R02.

## CSI-to-radar alignment

Each CSI record was matched to the nearest LD2450 record using
`collector_ts_us`. Device-local `ts_us` values were not compared.

| Metric | Nearest-message offset |
| --- | ---: |
| Compared CSI records | 40,519 |
| Median | 16.065 ms |
| p95 | 46.969 ms |
| p99 | 61.438 ms |
| Under 200 ms | 99.906% |
| Maximum | 349.807 ms |

The representative and p99 offsets satisfy the Week 5 target of less than
200 ms. Thirty-eight isolated CSI samples exceeded 200 ms around rare
inter-arrival gaps. They do not coincide with a missing radar sequence, MQTT
failure, queue drop, or node-offline transition. Week 6 data-quality checks
must flag such gaps instead of silently treating them as uniform samples.

## Acceptance decision

R02 passes the Week 5 synchronized RX1/LD2450 pilot acceptance:

- the physical radar power and UART paths are operational;
- UART parsing and radar frame sequencing are lossless during the run;
- CSI and ground truth are recorded together on a common collector clock;
- MQTT failure and accepted-queue drop counters remain unchanged;
- typical and p99 CSI-to-radar alignment remain below 200 ms.

This validates the pipeline for the planned labeled-data campaign. It does not
replace the required five scenarios with three repetitions each, and it does
not claim that every individual transport interval is below 200 ms.
