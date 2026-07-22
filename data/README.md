# VSense Recording Sessions

This directory contains recorded CSI sessions, detected motion events, and
manual ground-truth notes. Large local Parquet recordings are ignored by Git.

## Session ID

Every file belonging to the same experiment must use one shared session ID:

```text
YYYYMMDD_HHMMSS_location_scenario_rNN
```

Example:

```text
20260721_143000_office_mixed_r01
```

Use lowercase ASCII names and underscores. The repeat number starts at `r01`.

Standard scenario names:

- `empty`
- `walking`
- `hand_movement`
- `entry_exit`
- `mixed`

## File Names

Use a suffix to identify the contents of each file:

```text
<session_id>_csi.jsonl       Raw CSI packets
<session_id>_events.jsonl    Detected motion events
<session_id>_manual.csv      Manually recorded ground truth
```

Do not mix raw CSI packets and detected events in the same JSONL file.

## Detected Event Schema

Each line of an event JSONL file is a separate JSON object:

```json
{"schema_version":1,"event_type":"motion_start","ts_us":123456,"recorded_at":"2026-07-21T11:30:00+00:00","node_id":"node_01","motion_score":0.82,"threshold":0.75,"session_id":"20260721_143000_office_mixed_r01"}
```

`event_type` must be either `motion_start` or `motion_end`. `recorded_at` must
include a timezone so it can be compared with manually recorded events.

## Manual Ground Truth

Record the manually observed events in a CSV file with these columns:

```csv
event_type,recorded_at,node_id
motion_start,2026-07-21T14:00:00+03:00,node_01
motion_end,2026-07-21T14:00:30+03:00,node_01
```

## Recording

Record detected events:

```bash
python server/udp_collector.py --json-only \
  | python server/csi_live.py \
      --event-log data/events/<session_id>_events.jsonl \
      --session-id <session_id>
```

For the Week 3 Definition of Done, record a 30-minute empty-room run with zero
false alarms and verify that every real room entry produces `motion_start`
within two seconds.
