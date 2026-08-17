# Coarse zone prediction v1

The zone stage estimates a named room-level area from relative evidence across
the receiver nodes. It does not estimate an `(x, y)` coordinate and must not be
presented as precise indoor positioning.

## Pipeline

```text
motion_score + receiver health/status
→ per-node calibration
→ moving average
→ calibrated zone-signature comparison
→ hysteresis and confidence gate
→ zone_prediction
```

`server/config/zones.json` contains receiver signal calibration and the
expected relative receiver signature for each demo zone. The checked-in values
are safe starting values, not measured room calibration. Replace the
`motion_scale`, `rssi_reference`, and zone weights with values derived from the
final hardware placement without changing the message contract.

Two receivers can support more than two coarse zones when their relative
signatures differ. For example, `desk` can be RX1-dominant, `door` RX2-dominant,
and `window` balanced. Similar signatures produce low confidence and therefore
the explicit `unknown` zone rather than a forced answer.

## Standalone use

```bash
python server/live_activity_predictor.py \
  --artifact-dir dataset-v1/models/baseline_v1 \
  | python server/zone_predictor.py \
      --config server/config/zones.json
```

The stage preserves every input record and appends `zone_prediction` records:

```json
{
  "schema_version": 1,
  "message_type": "zone_prediction",
  "timestamp_us": 1786619298831549,
  "zone": "desk",
  "confidence": 0.78,
  "source_node": "rx_01",
  "node_scores": {"rx_01": 0.81, "rx_02": 0.19},
  "zone_scores": {"desk": 0.96, "door": 0.34, "window": 0.69},
  "method": "calibrated_receiver_signature",
  "coarse_location_only": true
}
```

Offline receivers are excluded. Ambiguous or unavailable evidence produces
`unknown`. An `empty_room` activity prediction produces `unoccupied`. The
inactivity alarm consumes fresh zone records and marks stale zone context as
`unknown`.
