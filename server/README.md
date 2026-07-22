# Server

This folder contains the platform-side scripts for CSI replay and live processing.

## Files

- `requirements.txt`: Python dependencies
- `csi_utils.py`: Shared CSI helper functions
- `csi_replay.py`: Replays recorded CSI data as a stream
- `csi_live.py`: Receives CSI stream and computes live motion score

## Week 3 Motion Event Logging

`csi_live.py` emits an event only when a node changes motion state:

- `STILL -> HAREKET`: `motion_start`
- `HAREKET -> STILL`: `motion_end`

Events are printed as JSON to stderr. Use `--event-log` to append them to a
JSONL file and `--session-id` to associate them with a recording session:

```bash
python server/udp_collector.py --json-only \
  | python server/csi_live.py \
      --event-log data/events/20260721_143000_office_mixed_r01_events.jsonl \
      --session-id 20260721_143000_office_mixed_r01
```

Each JSONL line follows event schema version 1:

```json
{"schema_version":1,"event_type":"motion_start","ts_us":123456,"recorded_at":"2026-07-21T11:30:00+00:00","node_id":"node_01","motion_score":0.82,"threshold":0.75,"session_id":"20260721_143000_office_mixed_r01"}
```

Required fields are `schema_version`, `event_type`, `ts_us`, `recorded_at`,
`node_id`, `motion_score`, and `threshold`. `session_id` is included when it
is supplied on the command line.

The recording session naming standard is documented in `data/README.md`.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt
```
