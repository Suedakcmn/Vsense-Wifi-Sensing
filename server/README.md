# VSense server — Week 4 MQTT/multi-node

`mqtt_collector.py` is now the canonical receiver. It subscribes to every
node's `csi`, `health`, retained `status`, and LD2450 ground-truth topics,
normalizes them into JSONL, optionally records the stream, and emits an `offline` state
after five seconds without any message. `udp_collector.py` remains only for
legacy experiments.

The final application pipeline is launched with `run_dashboard.py`:

```text
MQTT collector → activity predictor → zone predictor → inactivity alarm
→ FastAPI/WebSocket dashboard
```

See `docs/live_dashboard.md`, `docs/live_activity_prediction.md`, and
`docs/zone_prediction.md` for the final run commands and artifact contracts.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt
mosquitto -v
```

## Live multi-node pipeline

```bash
python server/mqtt_collector.py --host 127.0.0.1 \
  --record data/sessions/20260729_143000_office_multi_rx_r01_csi.jsonl \
  | python server/csi_live.py \
      --event-log data/events/20260729_143000_office_multi_rx_r01_events.jsonl \
      --session-id 20260729_143000_office_multi_rx_r01
```

For the multi-node graph, feed the same collector stream to the plotter:

```bash
python server/mqtt_collector.py --host 127.0.0.1 \
  | python server/csi_live_plot.py
```

Each receiver gets a separate colored motion-score line and independent filter
state. Offline nodes remain visible but their line is faded; the status box
shows connection state, motion state, latest score, and RSSI per node.

The output contains a separate motion state per `node_id` and lines such as
`node_id=rx_02 node_status=offline source=timeout`. Status/LWT messages normally
make disconnects visible immediately; the collector watchdog guarantees the
transition no later than `--offline-timeout` (default 5 seconds) after the last
CSI/health/status message.

Firmware and collector MQTT keepalive defaults are 30 seconds. Fast node
liveness is provided by CSI/health traffic plus the collector watchdog, not by
an unusually short MQTT keepalive.

Normalized MQTT records and valid UDP recordings include `recorded_at` and
`collector_ts_us`. Use `collector_ts_us` as the common Mac clock when aligning
multiple RX streams or future LD2450 radar data. Firmware `ts_us` remains useful
for device-local interval and jitter analysis.

## Test with two virtual receivers

Run the collector pipeline above, then start these in two terminals:

```bash
python server/csi_replay.py data/sessions/empty_room.jsonl \
  --transport mqtt --node-id rx_01 --override-node-id
```

```bash
python server/csi_replay.py data/sessions/walking.jsonl \
  --transport mqtt --node-id rx_02 --override-node-id
```

Replay publishes retained online/offline state and one health message per
second, so the same path can be tested without two physical boards. Stop one
process and verify that only that node changes to offline.

## Broker inspection and tests

```bash
mosquitto_sub -v -h localhost -t 'vsense/+/csi' -t 'vsense/+/health' -t 'vsense/+/status'
python -m unittest discover -s server -p 'test_*.py'
```

For an authenticated broker pass `--username` and `--password` to the collector.

## Week 5 recording CLI

Use `session_cli.py` to create a named CSI + LD2450 recording with metadata and
separate JSONL streams. Full wiring, message schema, commands, and validation
steps are documented in `docs/ld2450.md`.
