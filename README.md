# VSense Wi-Fi Sensing

VSense is a privacy-preserving indoor sensing prototype. ESP32-S3 receiver
nodes capture Wi-Fi Channel State Information (CSI), and a local pipeline uses
the signal changes to classify activity and raise an inactivity alert. An
LD2450 mmWave radar provides an independent occupancy
reference for the live dashboard.

The system does not capture images or audio. The final activity contract uses
`empty_room`, `walking`, `standing`, and `desk_work`.

## End-to-end pipeline

```text
ESP32-S3 TX → ESP32-S3 RX1/RX2 → MQTT collector
→ activity model → inactivity alarm
→ FastAPI/WebSocket → React dashboard
                         ↑
               LD2450 ground truth
```

The dashboard shows activity confidence and class probabilities, receiver
health, motion-score history, model/pipeline state, alarms, and
CSI-versus-radar occupancy agreement.

## Requirements

- Python 3.11
- Node.js 22 (the GitLab CI version)
- Mosquitto MQTT broker
- ESP-IDF 5.3.2 for firmware work

Create the application environment from the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r server/requirements.txt
npm --prefix web ci
npm --prefix web run build
```

Start the local broker in a separate terminal:

```bash
mosquitto -v
```

## Run the complete application

With the virtual environment active:

```bash
python server/run_dashboard.py \
  --mqtt-host 127.0.0.1 \
  --artifact-dir dataset-v1/models/baseline_v1 \
  --allow-legacy-artifact \
  --inactivity-seconds 300
```

Open <http://127.0.0.1:8000>. One `Ctrl+C` in the launcher terminal stops all
five pipeline stages.

For an authenticated broker, place the password in the environment instead of
the command line:

```bash
export VSENSE_MQTT_PASSWORD='replace-me'
python server/run_dashboard.py \
  --mqtt-host BROKER_IP \
  --mqtt-username USERNAME
```

See [the live dashboard runbook](docs/live_dashboard.md) for replay, short alarm
demo, and hardware-free LD2450 commands.

## Model artifacts

The live predictor supports versioned scikit-learn and TorchScript artifacts.
The artifact contract records the class order, receiver order, subcarriers,
window/stride, normalization, sample rate, and model version.

Validate an artifact before using it:

```bash
python server/validate_model_artifact.py \
  dataset-v1/models/baseline_v1 \
  --require-report
```

Package a selected final model reproducibly:

```bash
python server/package_model.py \
  --model /path/to/model.joblib \
  --config /path/to/feature_config.json \
  --metrics /path/to/metrics.json \
  --output dataset-v1/models/final_v1
```

The checked-in `baseline_v1` artifact exists to exercise the integration path;
its documented held-out macro-F1 is 0.271 and it must not be presented as the
selected final activity model. It also contains the retired `sitting` class;
final packaging accepts only the four-class project order.
The launcher refuses this legacy artifact unless `--allow-legacy-artifact` is
given explicitly. Never use that flag for final evaluation or the final demo.

## Verification

Run the same application checks used by GitLab CI:

```bash
python -m unittest discover -s server -p 'test_*.py'
python server/validate_model_artifact.py \
  dataset-v1/models/baseline_v1 \
  --require-report
npm --prefix web test
npm --prefix web run build
```

The firmware has separate TX, RX1, RX2, and LD2450 profiles. Use the explicit
build and flash commands in [the multi-node firmware guide](docs/multi_node_firmware.md)
and [the LD2450 guide](docs/ld2450.md); always confirm the USB port and generated
configuration before flashing.

## MQTT topics and data

Receiver records use these topic families:

```text
vsense/{node_id}/csi
vsense/{node_id}/health
vsense/{node_id}/status
```

The collector normalizes messages to JSONL and uses `collector_ts_us` as the
shared host clock for multi-receiver and radar alignment. Raw sessions and
generated experiment outputs are intentionally excluded from Git; preserve
their metadata and labels with the session tooling instead of committing large
recordings.

Detailed contracts are documented in:

- [Packet format](docs/packet_format.md)
- [Normalized data schema](docs/data_schema.md)
- [Live activity prediction](docs/live_activity_prediction.md)
- [Firmware design](docs/firmware_design.md)

## Current completion status

Implemented and integrated:

- multi-receiver MQTT collection and offline detection;
- versioned model adapters, artifact validation, and packaging;
- live activity, motion-score, alarm, and radar pipeline;
- FastAPI/WebSocket backend and React dashboard;
- bounded event/chart history, reconnect behavior, and visible pipeline state;
- one-command launcher and automated backend/frontend CI checks.

Still required before the final evaluation:

- select and freeze the final activity model from development folds;
- record and open the final holdout only after model selection;
- run the documented end-to-end hardware acceptance test and demo rehearsal.

These remaining measurements must be reported as observed. The holdout must not
be reused for model or threshold tuning.
