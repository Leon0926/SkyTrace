import React from "react";

function formatTimestamp(value) {
  if (!value) {
    return "Waiting for processing";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString();
}

export default function SystemActivity({ stats, analyzerStats, lastRefresh, errors }) {
  const totalKafkaEvents =
    Number(analyzerStats.location_reading || 0) +
    Number(analyzerStats.time_until_arrival_reading || 0);
  const activeErrors = Object.entries(errors).filter(([, value]) => value);

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Snapshot</p>
          <h2>System Activity</h2>
        </div>
      </div>

      <div className="activity-list">
        <div>
          <span>Processing updated</span>
          <strong>{formatTimestamp(stats.last_updated)}</strong>
        </div>
        <div>
          <span>Kafka events observed</span>
          <strong>{totalKafkaEvents.toLocaleString()}</strong>
        </div>
        <div>
          <span>Dashboard refreshed</span>
          <strong>{lastRefresh ? lastRefresh.toLocaleTimeString() : "Starting"}</strong>
        </div>
        <div>
          <span>Data sources</span>
          <strong>{activeErrors.length === 0 ? "All reachable" : `${activeErrors.length} issue(s)`}</strong>
        </div>
      </div>
    </section>
  );
}
