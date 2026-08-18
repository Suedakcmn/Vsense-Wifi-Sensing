# Live activity prediction

## Purpose

The live activity predictor completes the Week 6 inference path:

```text
RX1/RX2 CSI → MQTT collector → clean time window → shared ML features
→ saved model → activity_prediction JSONL
```

It consumes the normalized JSONL emitted by `server/mqtt_collector.py`. It does
not duplicate the training feature calculations: both training and inference
use `server/ml/features.py`.

The current `baseline_v1` artifact is an integration baseline, not a final
accuracy result. Its held-out test macro-F1 is 0.271, and it does not yet meet
the Week 6 target of meaningful accuracy in at least four classes. See
`dataset-v1/models/baseline_v1/README.md` for the complete honest evaluation.

## Model artifact contract

An artifact directory contains a model selected by `model_type`:

```text
<artifact-dir>/
├── feature_config.json
├── model.joblib or model.pt
├── metrics.json
├── manifest.json
└── README.md
```

At startup, the artifact loader selects the scikit-learn or lazy TorchScript
adapter and verifies that:

- the config schema version is supported;
- model and config class sets match;
- the fitted model expects the configured number of features;
- feature names are unique;
- window, stride, gap, node, and subcarrier settings are present;
- scikit-learn models support both `predict` and `predict_proba`;
- TorchScript models produce one logit per configured class.

Torch CNN artifacts additionally define `sample_rate_hz`, `normalization`,
`tensor_shape`, receiver order, and subcarrier order. The live adapter performs
time alignment, fixed-rate interpolation, and per-subcarrier z-score using the
artifact contract. PyTorch is imported only when a Torch artifact is selected.

Before every window prediction, the runtime feature names and ordering are
compared with `feature_config.json`. Inference stops with a clear contract error
instead of silently using reordered or incompatible features.

## Live MQTT pipeline

From the repository root, with the Python environment active and Mosquitto
reachable at `127.0.0.1:1883`:

```bash
python server/mqtt_collector.py \
  --host 127.0.0.1 \
  --client-id vsense-activity-collector \
  | python server/live_activity_predictor.py \
      --artifact-dir dataset-v1/models/baseline_v1
```

Use the actual broker IP instead of `127.0.0.1` when the broker runs on another
computer. Stop the pipeline with `Ctrl+C`; both processes terminate cleanly.

The predictor accepts normalized CSI rows for the nodes named in
`feature_config.json`. For `baseline_v1`, both `rx_01` and `rx_02` are required.
Health, node-status, ground-truth, model-status, and pipeline-status
records pass through for downstream stages. Raw CSI does not pass through, so
the web state is not flooded with high-rate samples. Unknown-node, malformed,
duplicate, out-of-order, and wrong-length CSI records do not produce
predictions.

## Hardware-free replay check

Start the live pipeline above. In another terminal, replay a real two-node
recording through the local MQTT broker:

```bash
python server/csi_replay.py \
  /path/to/session/csi.jsonl \
  --transport mqtt \
  --mqtt-host 127.0.0.1 \
  --mqtt-port 1883 \
  --limit 700 \
  --delay 0.002
```

The small delay avoids overwhelming the QoS 0 local replay path. A zero-delay
burst can drop enough messages to fail the same window-quality checks used by
the ML pipeline; it should not be used as evidence that inference is broken.

This path was verified with the `walking_r01` recording. The collector and
predictor emitted multiple `walking` predictions. That smoke test proves
transport and feature compatibility only; it does not replace the model's
held-out metrics.

## Output contract

Each completed clean window produces one compact JSON object on stdout:

```json
{
  "schema_version": 1,
  "message_type": "activity_prediction",
  "model_version": "baseline_v1",
  "window_start_us": 1786619296831549,
  "window_end_us": 1786619298831549,
  "activity": "walking",
  "confidence": 1.0,
  "probabilities": {
    "empty_room": 0.0,
    "walking": 1.0,
    "standing": 0.0,
    "desk_work": 0.0
  }
}
```

`confidence` is the selected activity's probability. Probability keys follow
the class order in `feature_config.json`, even if the saved estimator stores
its classes in a different internal order.

## Updating the model

The inference code does not hard-code the current window duration,
subcarriers, features, or class list. When a new model is selected, package its
compatible model file and `feature_config.json` together and point
`--artifact-dir` at that directory:

```bash
python server/live_activity_predictor.py \
  --artifact-dir dataset-v1/models/<new-model-version>
```

If the feature extractor changes incompatibly, increment `schema_version` and
update the inference adapter deliberately. Do not replace only `model.joblib`
or only `feature_config.json`.

Before deployment, run:

```bash
python server/validate_model_artifact.py \
  dataset-v1/models/<new-model-version> \
  --require-report \
  --require-final-classes
```

The final class order is `empty_room`, `walking`, `standing`, `desk_work`.
The checked-in baseline still contains the retired `sitting` class and remains
available only as a legacy integration fixture while the final model is being
selected.

## Verification

Run the complete server test suite:

```bash
python -m unittest discover -s server -p 'test_*.py'
```

The live predictor tests cover model/config mismatch, feature-order drift,
invalid vectors, missing nodes, CSI gaps, wrong CSI length, overlapping window
timing, malformed JSON input, prediction output, and clean interruption.
