import React from "react";

export default function AnomalyFeed({ anomalies, error }) {
  const recent = Array.isArray(anomalies) ? anomalies.slice(0, 6) : [];
  const tooHigh = recent.filter((item) => item.anomaly_type === "TooHigh").length;
  const tooLow = recent.filter((item) => item.anomaly_type === "TooLow").length;

  return (
    <section className="panel anomaly-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Detection</p>
          <h2>Anomaly Feed</h2>
        </div>
        <div className="feed-summary">
          <span>{tooHigh} high</span>
          <span>{tooLow} low</span>
        </div>
      </div>

      {error && <div className="inline-error">Anomaly service unavailable</div>}

      {!error && recent.length === 0 && (
        <div className="empty-state">No anomalies detected yet</div>
      )}

      {!error && recent.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Event</th>
                <th>Detail</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((item) => (
                <tr key={`${item.trace_id}-${item.timestamp}`}>
                  <td>
                    <span className={`status-pill ${item.anomaly_type === "TooHigh" ? "warn" : "info"}`}>
                      {item.anomaly_type}
                    </span>
                  </td>
                  <td>{item.event_id}</td>
                  <td>{item.description}</td>
                  <td>{item.timestamp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
