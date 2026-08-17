import test from "node:test";
import assert from "node:assert/strict";

import {
  createEmptyState,
  eventLabel,
  motionSeries,
  normalizeSnapshot,
  percentage,
  pipelineMessage,
  radarComparison,
  websocketUrl,
} from "./dashboardState.js";

test("creates isolated initial dashboard state", () => {
  const first = createEmptyState();
  const second = createEmptyState();
  first.nodes.rx_01 = { status: "online" };
  first.events.push({ message_type: "node_status" });
  assert.deepEqual(second.nodes, {});
  assert.deepEqual(second.events, []);
});

test("normalizes a dashboard snapshot", () => {
  const snapshot = normalizeSnapshot({
    message_type: "dashboard_state",
    revision: 4,
    latest_prediction: { activity: "walking" },
    nodes: { rx_01: { status: "online" } },
    events: [],
  });
  assert.equal(snapshot.revision, 4);
  assert.equal(snapshot.latest_prediction.activity, "walking");
  assert.equal(snapshot.nodes.rx_01.status, "online");
});

test("rejects non-dashboard records", () => {
  assert.equal(normalizeSnapshot(null), null);
  assert.equal(normalizeSnapshot({ message_type: "activity_prediction" }), null);
});

test("builds websocket URL for HTTP and HTTPS", () => {
  assert.equal(
    websocketUrl({ protocol: "http:", host: "localhost:5173" }),
    "ws://localhost:5173/ws",
  );
  assert.equal(
    websocketUrl({ protocol: "https:", host: "vsense.example" }),
    "wss://vsense.example/ws",
  );
});

test("formats confidence safely", () => {
  assert.equal(percentage(0.728), "73%");
  assert.equal(percentage(2), "100%");
  assert.equal(percentage(undefined), "—");
});

test("explains actionable pipeline states", () => {
  assert.match(
    pipelineMessage({ status: "waiting", reason: "missing_rx" }),
    /required receiver/,
  );
  assert.equal(pipelineMessage({ status: "ready" }), null);
});

test("formats known event types", () => {
  assert.equal(
    eventLabel({ message_type: "inactivity_alarm", status: "raised" }),
    "Inactivity alarm: raised",
  );
  assert.equal(
    eventLabel({ message_type: "node_status", node_id: "rx_01", status: "online" }),
    "rx_01: online",
  );
});

test("builds finite chart paths for receiver motion scores", () => {
  const series = motionSeries([
    { window_end_us: 1, scores: { rx_01: 0, rx_02: 2 } },
    { window_end_us: 2, scores: { rx_01: 1, rx_02: 4 } },
  ]);
  assert.deepEqual(series.map((value) => value.nodeId), ["rx_01", "rx_02"]);
  assert.equal(series[0].latest, 1);
  assert.match(series[0].path, /^0,32 100,/);
  assert.equal(motionSeries([]).length, 0);
});

test("compares CSI and radar occupancy without claiming activity accuracy", () => {
  assert.deepEqual(
    radarComparison({ activity: "walking" }, { targets: [{ target_id: 1 }] }),
    { available: true, occupied: true, agreement: true, targets: [{ target_id: 1 }] },
  );
  assert.equal(radarComparison({ activity: "empty_room" }, { targets: [{}] }).agreement, false);
  assert.equal(radarComparison(null, null).available, false);
});
