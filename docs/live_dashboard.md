# Live dashboard runbook

## Setup

From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt
npm --prefix web install
npm --prefix web run build
```

Start Mosquitto separately if it is not already running:

```bash
mosquitto -v
```

## Start the complete pipeline

The launcher connects the four existing stages and serves the built dashboard:

```bash
python server/run_dashboard.py \
  --mqtt-host 127.0.0.1 \
  --artifact-dir dataset-v1/models/baseline_v1 \
  --inactivity-seconds 300
```

Open `http://127.0.0.1:8000`. Stop every child process with one `Ctrl+C` in
the launcher terminal.

For an authenticated broker, keep the password out of shell history:

```bash
export VSENSE_MQTT_PASSWORD='replace-me'
python server/run_dashboard.py \
  --mqtt-host BROKER_IP \
  --mqtt-username USERNAME
```

The launcher reads the variable named by `--mqtt-password-env` and never
requires a password command-line argument.

## Hardware-free demo

Start the launcher, then replay a real two-node CSI session in a second
terminal:

```bash
python server/csi_replay.py /path/to/session/csi.jsonl \
  --transport mqtt \
  --mqtt-host 127.0.0.1 \
  --limit 1200 \
  --delay 0.002
```

The 2 ms delay avoids overwhelming the QoS 0 replay path. The dashboard should
show both receiver nodes, update the current activity, and draw a separate
relative motion-score line for each receiver. The chart uses the existing CSI
variance baseline and is intended for movement trends rather than comparison of
absolute scores between receivers. The baseline model is
only an integration artifact; its documented held-out macro-F1 remains 0.271.
Do not interpret one successful replay window as a model-accuracy result.

For a short alarm demonstration, restart the launcher with a small threshold:

```bash
python server/run_dashboard.py --inactivity-seconds 10
```

Production or evaluation runs must use the agreed real threshold rather than
the shortened demo value.

## Verification

```bash
python -m unittest discover -s server -p 'test_*.py'
npm --prefix web test
npm --prefix web run build
```

The dashboard API also exposes:

- `GET /health`
- `GET /api/state`
- `WebSocket /ws`
