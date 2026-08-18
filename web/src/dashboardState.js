export function createEmptyState() {
  return {
    revision: 0,
    latest_prediction: null,
    active_alarm: null,
    latest_zone: null,
    motion_scores: [],
    nodes: {},
    events: [],
  };
}

export function normalizeSnapshot(value) {
  if (!value || value.message_type !== "dashboard_state") {
    return null;
  }
  return {
    revision: Number.isInteger(value.revision) ? value.revision : 0,
    latest_prediction: value.latest_prediction ?? null,
    active_alarm: value.active_alarm ?? null,
    latest_zone: value.latest_zone ?? null,
    motion_scores: Array.isArray(value.motion_scores) ? value.motion_scores : [],
    nodes: value.nodes && typeof value.nodes === "object" ? value.nodes : {},
    events: Array.isArray(value.events) ? value.events : [],
  };
}

export function motionSeries(points) {
  if (!Array.isArray(points) || !points.length) return [];
  const nodeIds = [...new Set(points.flatMap((point) => Object.keys(point?.scores ?? {})))].sort();
  const values = points.flatMap((point) => Object.values(point?.scores ?? {}))
    .map(Number)
    .filter(Number.isFinite);
  const maximum = Math.max(...values, 0);
  const scale = maximum > 0 ? maximum : 1;
  const denominator = Math.max(points.length - 1, 1);
  return nodeIds.map((nodeId) => ({
    nodeId,
    latest: Number(points.at(-1)?.scores?.[nodeId]),
    path: points.map((point, index) => {
      const value = Number(point?.scores?.[nodeId]);
      if (!Number.isFinite(value)) return null;
      return `${(index / denominator) * 100},${32 - (Math.max(0, value) / scale) * 30}`;
    }).filter(Boolean).join(" "),
  }));
}

export function websocketUrl(locationValue = window.location) {
  const protocol = locationValue.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${locationValue.host}/ws`;
}

export function percentage(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  return `${Math.round(Math.max(0, Math.min(1, number)) * 100)}%`;
}

export function eventLabel(event) {
  switch (event?.message_type) {
    case "activity_prediction":
      return `Activity: ${event.activity ?? "unknown"}`;
    case "inactivity_alarm":
      return `Alarm ${event.status ?? "unknown"}: ${event.zone ?? "unknown"}`;
    case "node_status":
      return `${event.node_id ?? "node"}: ${event.status ?? "unknown"}`;
    case "zone_prediction":
      return `Zone: ${event.zone ?? "unknown"}`;
    default:
      return event?.message_type ?? "event";
  }
}
