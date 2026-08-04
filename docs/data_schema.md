# VSense CSI Data Schema

## Purpose

This document describes the expected CSI dataset format used by the Week 1 analysis and replay/live pipeline.

The dataset itself is not committed to Git because Parquet files may be large. Local CSI recordings should be placed under the data/ directory.

## Canonical schema v2 (Week 4)

The preferred logical format for replay/live testing is:

| Column | Description |
|---|---|
| ts_us | Timestamp in microseconds |
| node_id | Receiver node identifier, for example rx_01 |
| rssi | Received signal strength |
| csi | Raw CSI values in [imag0, real0, imag1, real1, ...] format |
| label | Optional label for recorded data only |
| schema_version | `2` for CSI/telemetry; `1` for LD2450 ground truth |
| message_type | `csi`, `health`, `node_status`, or `ground_truth` |
| recorded_at | Collector receive time in UTC ISO-8601 form |
| collector_ts_us | Collector receive time as Unix epoch microseconds |

`node_id` is mandatory in stored multi-node data. The collector derives it
from `vsense/{node_id}/...`; topic identity overrides a conflicting payload
value. Health rows carry firmware telemetry. Node-state rows carry `status`
(`online`/`offline`) and `source` (`mqtt_status`, `csi`, `health`, or `timeout`).
The firmware `ts_us` value is device uptime and is not shared across RX nodes.
Use `collector_ts_us` to align CSI from multiple RX nodes or LD2450 radar data
on the collector's common clock; keep `ts_us` for device-side interval and
jitter analysis.

## LD2450 ground truth

The radar bridge publishes firmware records to `vsense/gt/ld2450_01`. The
collector normalizes them as `message_type: ground_truth`, uses the topic node
identity, and records them in `ground_truth.jsonl`. Ground-truth schema version
1 requires `ts_us`, `frame_seq`, and a `targets` list. Each present target has
`target_id`, `x_mm`, `y_mm`, `speed_cm_s`, and `resolution_mm`;
`distance_mm` is optional. An empty targets list represents a valid no-target
frame. See `docs/ld2450.md` for the full contract and campaign commands.

Example logical row:

    {
      "ts_us": 0,
      "node_id": "rx_01",
      "rssi": -55,
      "csi": [3, 4, -2, 5],
      "label": "empty"
    }

## Important Note About label

label is not expected from ESP32 firmware.

It may exist only in recorded datasets for analysis, validation, or ML experiments.

Real RX firmware should send CSI and metadata, not activity labels.

## Supported Analysis Format

Some converted datasets may store amplitude directly instead of raw CSI.

Supported amplitude-based columns:

| Column | Description |
|---|---|
| file_name | Original recording file name |
| ts_us | Timestamp |
| rssi_a, rssi_b, rssi_c | RSSI values from different antennas/chains, if available |
| csi_amplitude | Precomputed CSI amplitude vector |

If csi_amplitude exists, analysis scripts use it directly.

If only csi exists, analysis scripts convert raw CSI to amplitude using:

    amplitude = sqrt(real^2 + imag^2)

## Relationship to Firmware Packet Format

The firmware-side packet format may call the raw payload csi_payload.

The server-side JSON/replay format calls the same logical data csi.

Both represent raw CSI values.

## Local Data Files

Expected local paths:

    data/<provided_recording>.parquet
    data/csi_final.parquet

These files are ignored by Git through .gitignore.

## Data Checks To Perform

For every dataset, check:

- Number of rows
- Column names
- Timestamp unit
- CSI vector length
- Missing values
- Whether CSI is raw or already amplitude
- Whether labels are present
- Whether multiple recordings are mixed in one Parquet file

## Actual Tested Dataset

Local test file:

    data/csi_final.parquet

This file is not committed to Git because it is large.

Observed columns:

| Column | Description |
|---|---|
| file_name | Original CSI recording file name |
| ts_us | Timestamp value from the recording |
| rssi_a | RSSI value for antenna/chain A |
| rssi_b | RSSI value for antenna/chain B |
| rssi_c | RSSI value for antenna/chain C |
| csi_amplitude | Precomputed CSI amplitude vector |

Important observation:

This dataset does not contain raw `csi` values. It contains precomputed `csi_amplitude`.

Therefore:

- `server/analyze_recording.py` can use this dataset directly.
- `server/csi_replay.py` and `server/csi_live.py` need `csi_amplitude` compatibility before replay/live testing.

Local samples used for testing:

    data/csi_sample_5k.parquet
    data/csi_sample_20k.parquet

Generated local outputs:

    outputs/sample_5k_heatmap.png
    outputs/sample_5k_motion_score.png
    outputs/sample_20k_heatmap.png
    outputs/sample_20k_motion_score.png

These data and output files are ignored by Git.
