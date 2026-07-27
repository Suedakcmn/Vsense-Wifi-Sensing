# CSI Pilot Measurements — 27 July 2026

## Setup

- TX node: `tx_01`
- RX node: `rx_01`
- CSI length: 256 bytes
- RX forwarding: every second accepted CSI frame
- Transport: UDP and MQTT
- Wi-Fi channel observed during recordings: 1

## Transport verification

The rate-verification session recorded 3,031 frames over 64.30 seconds.

- Effective rate: 47.12 CSI frames/s
- Frame-count step: consistently 2
- RSSI mean: -41.37 dB
- RSSI standard deviation: 1.36 dB
- Invalid frames: 0
- CSI saturation: none

## Pilot recordings

### Empty room r02

- File: `20260727_140844_office_empty_r02_csi.jsonl`
- Duration: 912.53 seconds
- Frames: 45,377
- Effective rate: 49.73 frames/s
- Estimated missing-frame ratio: 3.08%
- CSI length: all frames 256 bytes
- Trimmed RSSI mean: -54.78 dB
- Trimmed RSSI standard deviation: 0.76 dB

### Walking r01

- File: `20260727_143051_office_walking_r01_csi.jsonl`
- Duration: 224.43 seconds
- Frames: 11,826
- Effective rate: 52.69 frames/s
- Estimated missing-frame ratio: 0.076%
- CSI length: all frames 256 bytes
- RSSI standard deviation: 0.61 dB

### Hand movement r01

- File: `20260727_143745_office_hand_movement_r01_csi.jsonl`
- Duration: 181.36 seconds
- Frames: 9,932
- Effective rate: 54.76 frames/s
- Estimated missing-frame ratio: 0.38%
- CSI length: all frames 256 bytes
- RSSI standard deviation: 1.43 dB

## Signal-processing findings

The current fixed threshold and previously selected subcarriers do not
generalize across the new approximately 50 Hz sessions.

- The fixed thresholds `0.75` and `0.30` should not be treated as validated.
- Absolute motion-score scale changes substantially between sessions.
- The previous selected-subcarrier list detects walking weakly but does not
  reliably detect hand movement.
- A candidate set found in both walking and hand-movement pilots is:
  `55,56,54,57,45,44,52,50,51,46,58,53,48,43,75,61,47,96,42,77`.
- This candidate list was derived from the pilot sessions and must be tested
  unchanged on independent recordings before adoption.

## Current conclusion

The firmware, UDP transport, MQTT transport, and recording pipeline work.
The present bottleneck is motion-score calibration and reliable labeling, not
raw CSI acquisition.

## Next actions

1. Create a timed recorder that writes CSI and phase-level ground truth.
2. Use a 60-second empty-room calibration period for every session.
3. Normalize live scores relative to the session baseline instead of using a
   global absolute threshold.
4. Validate candidate subcarriers on independent `r02` recordings.
5. Add LD2450 ground truth before the main ML dataset campaign.
6. Keep raw CSI files outside normal Git history and share them through
   approved shared storage with SHA-256 checksums.
