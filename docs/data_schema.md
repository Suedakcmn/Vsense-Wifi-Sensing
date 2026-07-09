# VSense CSI Data Schema

## Purpose

This document describes the expected CSI dataset format used by the Week 1 analysis and replay/live pipeline.

The dataset itself is not committed to Git because Parquet files may be large. Local CSI recordings should be placed under the data/ directory.

## Canonical Week 1 Server Format

The preferred logical format for replay/live testing is:

| Column | Description |
|---|---|
| ts_us | Timestamp in microseconds |
| node_id | Receiver node identifier, for example rx_01 |
| rssi | Received signal strength |
| csi | Raw CSI values in [imag0, real0, imag1, real1, ...] format |
| label | Optional label for recorded data only |

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
