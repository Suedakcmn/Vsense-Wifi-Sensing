import { useEffect, useMemo, useState } from "react";

import {
  EMPTY_STATE,
  eventLabel,
  motionSeries,
  normalizeSnapshot,
  percentage,
  pipelineMessage,
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
  const [state, setState] = useState(EMPTY_STATE);
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
        <div><dt>RSSI</dt><dd>{node.health?.last_rssi ?? node.health?.rssi ?? "—"} dBm</dd></div>
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

function ZoneCard({ prediction }) {
  const scores = Object.entries(prediction?.node_scores ?? {}).sort((a, b) => b[1] - a[1]);
  const zone = prediction?.zone ?? "unknown";
  const configuredZones = Object.keys(prediction?.zone_scores ?? {});
  const zones = configuredZones.length ? configuredZones : ["desk", "door", "window"];
  return (
    <article className="zone-card panel">
      <p className="eyebrow">Estimated zone</p>
      <div className={`zone-map zone-${zone}`}>
        {zones.map((zoneName) => (
          <div className={`zone-area ${zoneName === zone ? "active" : ""}`} key={zoneName}>
            <span>{zoneName}</span>
            {prediction?.zone_scores?.[zoneName] !== undefined && (
              <small>{percentage(prediction.zone_scores[zoneName])}</small>
            )}
          </div>
        ))}
        {(zone === "unknown" || zone === "unoccupied") && (
          <div className="zone-overlay">{zone}</div>
        )}
      </div>
      <dl className="zone-details">
        <div><dt>Confidence</dt><dd>{percentage(prediction?.confidence)}</dd></div>
        <div><dt>Source</dt><dd>{prediction?.source_node ?? "—"}</dd></div>
        <div><dt>Resolution</dt><dd>Coarse zone</dd></div>
      </dl>
      {scores.length > 0 && (
        <div className="zone-scores">
          {scores.map(([nodeId, score]) => (
            <div key={nodeId}>
              <span>{nodeId}</span>
              <div className="bar"><span style={{ width: percentage(score) }} /></div>
              <strong>{percentage(score)}</strong>
            </div>
          ))}
        </div>
      )}
      <p className="muted motion-note">Receiver comparison estimates a room-level zone, not a point coordinate.</p>
    </article>
  );
}

function ModelCard({ model, prediction }) {
  const value = model ?? (prediction ? {
    model_version: prediction.model_version,
    status: "ready",
  } : null);
  return (
    <section className="panel model-strip">
      <div><span>Model</span><strong>{value?.model_version ?? "Waiting"}</strong></div>
      <div><span>Type</span><strong>{value?.model_type ?? "—"}</strong></div>
      <div><span>Window</span><strong>{value?.window_seconds ? `${value.window_seconds} s` : "—"}</strong></div>
      <div><span>Normalization</span><strong>{value?.normalization ?? "—"}</strong></div>
      <div><span>Status</span><strong className={value?.status === "ready" ? "agree" : ""}>{value?.status ?? "waiting"}</strong></div>
    </section>
  );
}

export default function App() {
  const { state, connection } = useDashboardSocket();
  const prediction = state.latest_prediction;
  const probabilities = prediction?.probabilities ?? {};
  const nodes = useMemo(() => Object.values(state.nodes), [state.nodes]);
  const events = [...state.events].reverse().slice(0, 12);
  const predictorStatus = state.pipeline_status.activity_predictor;
  const statusMessage = pipelineMessage(predictorStatus);

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

      {statusMessage && (
        <section className="pipeline-banner" role="status">
          <strong>{statusMessage}</strong>
          {predictorStatus?.details?.missing_nodes?.length > 0 && (
            <span>Missing: {predictorStatus.details.missing_nodes.join(", ")}</span>
          )}
        </section>
      )}

      <ModelCard model={state.model_status} prediction={prediction} />

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

        <ZoneCard prediction={state.latest_zone} />
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
