import { useEffect, useMemo, useState } from "react";

import {
  createEmptyState,
  eventLabel,
  motionSeries,
  normalizeSnapshot,
  percentage,
  radarComparison,
  websocketUrl,
} from "./dashboardState.js";

const ACTIVITY_LABELS = {
  empty_room: "Empty room",
  walking: "Walking",
  sitting: "Sitting",
  standing: "Standing",
  desk_work: "Desk work",
};

function useDashboardSocket() {
  const [state, setState] = useState(createEmptyState);
  const [connection, setConnection] = useState("connecting");

  useEffect(() => {
    let socket;
    let reconnectTimer;
    let stopped = false;

    const connect = () => {
      setConnection("connecting");
      socket = new WebSocket(websocketUrl());
      socket.onopen = () => setConnection("connected");
      socket.onmessage = (message) => {
        try {
          const snapshot = normalizeSnapshot(JSON.parse(message.data));
          if (snapshot) {
            setState(snapshot);
          }
        } catch {
          // Ignore a malformed frame and keep the last valid dashboard state.
        }
      };
      socket.onerror = () => socket.close();
      socket.onclose = () => {
        if (!stopped) {
          setConnection("disconnected");
          reconnectTimer = window.setTimeout(connect, 1500);
        }
      };
    };

    connect();
    return () => {
      stopped = true;
      window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);

  return { state, connection };
}

function NodeCard({ node }) {
  const status = node.status ?? "unknown";
  const pps = node.health?.csi_pps ?? node.health?.csi_forwarded_pps;
  return (
    <article className="node-card">
      <div className="card-title-row">
        <h3>{node.node_id}</h3>
        <span className={`status-pill ${status}`}>{status}</span>
      </div>
      <dl>
        <div><dt>CSI rate</dt><dd>{pps ?? "—"} pps</dd></div>
        <div><dt>RSSI</dt><dd>{node.health?.rssi ?? "—"} dBm</dd></div>
        <div><dt>Source</dt><dd>{node.status_source ?? "—"}</dd></div>
      </dl>
    </article>
  );
}

function MotionChart({ points }) {
  const series = motionSeries(points);
  return (
    <section className="panel section-block motion-panel">
      <div className="section-heading">
        <div><p className="eyebrow">CSI movement</p><h2>Live motion score</h2></div>
        <span>{points.length} recent windows</span>
      </div>
      {series.length ? (
        <>
          <div className="motion-chart" role="img" aria-label="Receiver motion score history">
            <svg viewBox="0 0 100 34" preserveAspectRatio="none">
              <line x1="0" y1="32" x2="100" y2="32" className="chart-axis" />
              {series.map((line, index) => (
                <polyline key={line.nodeId} points={line.path} className={`motion-line motion-line-${index % 3}`} vectorEffect="non-scaling-stroke" />
              ))}
            </svg>
          </div>
          <div className="motion-legend">
            {series.map((line, index) => (
              <span key={line.nodeId} className={`motion-key motion-key-${index % 3}`}>
                {line.nodeId}: {Number.isFinite(line.latest) ? line.latest.toFixed(2) : "—"}
              </span>
            ))}
          </div>
          <p className="muted motion-note">Relative CSI variance; use the trend, not the raw value, to compare movement over time.</p>
        </>
      ) : <p className="empty-message">Waiting for clean CSI windows...</p>}
    </section>
  );
}

function RadarReference({ prediction, groundTruth }) {
  const radar = radarComparison(prediction, groundTruth);
  return (
    <section className="panel section-block radar-panel">
      <div className="section-heading">
        <div><p className="eyebrow">mmWave reference</p><h2>LD2450 comparison</h2></div>
        <span>{groundTruth?.node_id ?? "Waiting for radar"}</span>
      </div>
      {!radar.available ? <p className="empty-message">Waiting for LD2450 ground-truth frames...</p> : (
        <>
          <div className="radar-summary">
            <div><span>Radar occupancy</span><strong>{radar.occupied ? "Occupied" : "Empty"}</strong></div>
            <div><span>Detected targets</span><strong>{radar.targets.length}</strong></div>
            <div><span>CSI/radar occupancy</span><strong className={radar.agreement === false ? "disagree" : "agree"}>{radar.agreement === null ? "Waiting for CSI" : radar.agreement ? "Agreement" : "Mismatch"}</strong></div>
          </div>
          {radar.targets.length > 0 && (
            <div className="radar-targets">
              {radar.targets.map((target) => (
                <div key={target.target_id}>
                  <strong>Target {target.target_id}</strong>
                  <span>X {target.x_mm} mm</span><span>Y {target.y_mm} mm</span><span>{target.speed_cm_s} cm/s</span>
                </div>
              ))}
            </div>
          )}
          <p className="muted motion-note">Agreement compares occupied versus empty only; LD2450 does not provide activity-class labels.</p>
        </>
      )}
    </section>
  );
}

export default function App() {
  const { state, connection } = useDashboardSocket();
  const prediction = state.latest_prediction;
  const probabilities = prediction?.probabilities ?? {};
  const nodes = useMemo(() => Object.values(state.nodes), [state.nodes]);
  const events = [...state.events].reverse().slice(0, 12);
  const zone = state.latest_zone?.zone ?? prediction?.zone ?? "unknown";

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Privacy-first Wi-Fi sensing</p>
          <h1>VSense Live</h1>
          <p className="subtitle">Activity, receiver health and inactivity alerts.</p>
        </div>
        <div className={`connection ${connection}`}>
          <span className="connection-dot" />
          {connection}
        </div>
      </header>

      {state.active_alarm && (
        <section className="alarm-banner" aria-live="assertive">
          <div>
            <p className="eyebrow">Inactivity alert</p>
            <strong>{state.active_alarm.zone ?? "Unknown zone"}</strong>
          </div>
          <span>{Math.round(state.active_alarm.inactive_seconds)} seconds inactive</span>
        </section>
      )}

      <section className="overview-grid">
        <article className="activity-card panel">
          <p className="eyebrow">Current activity</p>
          <div className="activity-value">
            {ACTIVITY_LABELS[prediction?.activity] ?? prediction?.activity ?? "Waiting for CSI"}
          </div>
          <div className="confidence-row">
            <span>Confidence</span>
            <strong>{percentage(prediction?.confidence)}</strong>
          </div>
          <div className="probability-list">
            {Object.entries(ACTIVITY_LABELS).map(([key, label]) => (
              <div className="probability" key={key}>
                <div><span>{label}</span><span>{percentage(probabilities[key])}</span></div>
                <div className="bar"><span style={{ width: percentage(probabilities[key]) === "—" ? "0%" : percentage(probabilities[key]) }} /></div>
              </div>
            ))}
          </div>
        </article>

        <article className="zone-card panel">
          <p className="eyebrow">Estimated zone</p>
          <div className="zone-map">
            <div className="zone-marker" />
            <span>{zone}</span>
          </div>
          <p className="muted">
            Coarse zone output will appear here when the signal comparison module is connected.
          </p>
        </article>
      </section>

      <MotionChart points={state.motion_scores} />
      <RadarReference prediction={prediction} groundTruth={state.latest_ground_truth} />

      <section className="panel section-block">
        <div className="section-heading">
          <div><p className="eyebrow">Receivers</p><h2>Node health</h2></div>
          <span>{nodes.length} known nodes</span>
        </div>
        <div className="node-grid">
          {nodes.length ? nodes.map((node) => <NodeCard key={node.node_id} node={node} />) : (
            <p className="empty-message">Waiting for receiver status...</p>
          )}
        </div>
      </section>

      <section className="panel section-block">
        <div className="section-heading">
          <div><p className="eyebrow">Live feed</p><h2>Recent events</h2></div>
          <span>Revision {state.revision}</span>
        </div>
        <ol className="event-list">
          {events.length ? events.map((event, index) => (
            <li key={`${event.message_type}-${event.timestamp_us ?? event.window_end_us ?? index}-${index}`}>
              <span className={`event-icon ${event.message_type}`} />
              <div><strong>{eventLabel(event)}</strong><small>{event.reason ?? event.source ?? "live update"}</small></div>
            </li>
          )) : <li className="empty-message">No live events yet.</li>}
        </ol>
      </section>
    </main>
  );
}
