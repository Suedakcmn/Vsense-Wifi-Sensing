# Dashboard 15-minute soak test — 14 August 2026

## Purpose

Run a preliminary wall-clock stability check of the live two-receiver software
path before the required one-hour hardware acceptance test.

This is a replay-based software test. It does not replace the Week 7 DoD run
with two or more physical receiver nodes.

## Setup

- Branch: `feat/week8-alarm-demo`
- Commit: `c668162`
- Python: 3.11 virtual environment
- MQTT broker: Mosquitto 2.1.2 on `127.0.0.1:18884`
- Dashboard: `127.0.0.1:8768`
- Model artifact: `dataset-v1/models/baseline_v1`
- Offline timeout: 5 seconds
- Inactivity threshold: 300 seconds
- Replay session: `20260810_145706_lab_empty_room_r02`
- Replay delay: 6.2 ms per recorded row

The isolated ports avoided interference with any manually running broker or
dashboard instance.

## Procedure

1. Start an isolated Mosquitto broker.
2. Start the complete collector → predictor → alarm → dashboard pipeline.
3. Verify `GET /health`, `GET /api/state`, and the initial WebSocket snapshot.
4. Replay synchronized RX1/RX2 CSI for more than 15 minutes of wall-clock time.
5. Poll API state throughout the run.
6. Reconnect new WebSocket clients during the run and compare their snapshot
   revision with the HTTP API revision.
7. Stop the replay and verify both nodes become offline after the configured
   timeout while the dashboard remains healthy.
8. Stop the launcher with one interrupt and verify clean child-process shutdown.

## Results

| Check | Result |
| --- | --- |
| Replay wall-clock duration | 15 minutes 42 seconds |
| CSI rows replayed | 121,038 |
| Final dashboard revision after timeout | 3,795 |
| Activity predictions continued | PASS (`empty_room`) |
| Motion-score history continued | PASS |
| RX1 and RX2 remained online during replay | PASS |
| Event history stayed bounded | PASS (100 records) |
| Motion history stayed bounded | PASS (100 records) |
| HTTP health remained available | PASS |
| New WebSocket clients received current state | PASS |
| API and WebSocket revisions matched at checks | PASS |
| RX1/RX2 became offline after replay | PASS |
| Dashboard remained healthy after data stopped | PASS |
| Launcher shutdown | PASS (exit code 0) |

Observed revision checkpoints increased monotonically from 465 through 779,
1,171, 1,445, 1,777, 2,049, 2,321, 2,667, 2,953, 3,255, and finally 3,795.
No traceback or pipeline-stage exit was observed.

## Interpretation

The software pipeline passed this preliminary 15-minute stability run. The
bounded state histories prevented event and motion-score lists from growing
beyond their configured limit, and reconnecting clients continued to receive a
current snapshot.

The `empty_room` prediction and confidence values are model outputs, not a
model-accuracy conclusion. This test measures transport and service continuity.

## Remaining acceptance work

- Run the Week 7 DoD test for one uninterrupted hour with at least two physical
  receiver nodes.
- Zone prediction was listed as a possible follow-up at the time of this run;
  it was later removed from the final project scope.
- Include live LD2450 ground truth in the hardware run.
- Record process memory and CPU usage during the one-hour run.
- Verify physical node disconnect and reconnect behavior, not only replay
  status/timeout behavior.
