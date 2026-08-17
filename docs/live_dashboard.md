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

The launcher connects the collector, model, zone, alarm, and web stages and
serves the built dashboard:

```bash
python server/run_dashboard.py \
  --mqtt-host 127.0.0.1 \
  --artifact-dir dataset-v1/models/baseline_v1 \
  --zone-config server/config/zones.json \
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

The model strip reports the loaded artifact contract. Pipeline warnings explain
missing receivers or a window that is still filling. The zone card reports the
coarse zone, confidence, source receiver, and normalized receiver evidence.
Zone calibration and limitations are documented in `docs/zone_prediction.md`.

Validate or package a final model before launching it:

```bash
python server/validate_model_artifact.py dataset-v1/models/final_v1

python server/package_model.py \
  --model /path/to/model.joblib \
  --config /path/to/feature_config.json \
  --metrics /path/to/metrics.json \
  --output dataset-v1/models/final_v1
```

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

With the 10-second demo threshold, replay the recorded inactive session:

```bash
python server/csi_replay.py \
  /path/to/20260811_132130_lab_sitting_r02/csi.jsonl \
  --transport mqtt \
  --mqtt-host 127.0.0.1 \
  --limit 5000 \
  --delay 0.002
```

The current baseline predicts this recording as `standing`, not `sitting`.
Both are intentionally inactive classes, so the dashboard raises the alarm
after 10 seconds of recording time. This verifies the alarm path but also
demonstrates why the baseline's activity-class accuracy must not be overstated.

## Hardware-free LD2450 comparison

While the launcher is running, publish simulated radar reference frames from a
separate terminal:

```bash
python server/ld2450_simulator.py \
  --transport mqtt \
  --broker-host 127.0.0.1 \
  --duration-seconds 10 \
  --target-count 1
```

The LD2450 panel shows occupancy, target count, target coordinates, speed, and
CSI/radar occupancy agreement. This agreement means only empty versus occupied;
the radar does not provide walking, sitting, standing, or desk-work labels, so
the panel must not present it as activity-class accuracy.

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
