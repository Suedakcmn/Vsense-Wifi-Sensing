export const EMPTY_STATE = Object.freeze({
  revision: 0,
  latest_prediction: null,
  active_alarm: null,
  latest_zone: null,
  nodes: {},
  events: [],
});

export function normalizeSnapshot(value) {
  if (!value || value.message_type !== "dashboard_state") {
    return null;
  }
  return {
    revision: Number.isInteger(value.revision) ? value.revision : 0,
    latest_prediction: value.latest_prediction ?? null,
    active_alarm: value.active_alarm ?? null,
    latest_zone: value.latest_zone ?? null,
    nodes: value.nodes && typeof value.nodes === "object" ? value.nodes : {},
    events: Array.isArray(value.events) ? value.events : [],
  };
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
