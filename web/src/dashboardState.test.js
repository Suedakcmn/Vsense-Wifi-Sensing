import test from "node:test";
import assert from "node:assert/strict";

import {
  createEmptyState,
  eventLabel,
  normalizeSnapshot,
  percentage,
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

test("formats known event types", () => {
  assert.equal(
    eventLabel({ message_type: "inactivity_alarm", status: "raised", zone: "office" }),
    "Alarm raised: office",
  );
  assert.equal(
    eventLabel({ message_type: "node_status", node_id: "rx_01", status: "online" }),
    "rx_01: online",
  );
});
