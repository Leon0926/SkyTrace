import React from "react";

const SERVICE_LABELS = {
  receiver: "Receiver",
  storage: "Storage",
  processing: "Processing",
  analyzer: "Analyzer",
  anomaly_detector: "Anomaly Detector"
};

function getServiceState(message) {
  if (!message) {
    return "unknown";
  }

  return String(message).toLowerCase().includes("unavailable") ? "down" : "healthy";
}

export default function ServiceHealth({ health, error }) {
  const serviceNames = Object.keys(SERVICE_LABELS);

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Runtime</p>
          <h2>Service Health</h2>
        </div>
        {error && <span className="status-pill down">Check offline</span>}
      </div>

      <div className="service-grid">
        {serviceNames.map((service) => {
          const state = getServiceState(health[service]);
          const detail = health[service] || "Waiting for first check";

          return (
            <article className="service-card" key={service}>
              <div className="service-title">
                <span className={`status-dot ${state}`} aria-hidden="true" />
                <h3>{SERVICE_LABELS[service]}</h3>
              </div>
              <p>{detail}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}
