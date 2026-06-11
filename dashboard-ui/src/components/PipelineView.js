import React from "react";

const STEPS = [
  "Receiver",
  "Kafka",
  "Storage",
  "Processing",
  "Dashboard"
];

const SIDE_STEPS = ["Analyzer", "Anomaly Detector"];

export default function PipelineView() {
  return (
    <section className="panel pipeline-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Flow</p>
          <h2>Telemetry Pipeline</h2>
        </div>
      </div>

      <div className="pipeline-row">
        {STEPS.map((step, index) => (
          <React.Fragment key={step}>
            <div className="pipeline-node">{step}</div>
            {index < STEPS.length - 1 && <div className="pipeline-line" aria-hidden="true" />}
          </React.Fragment>
        ))}
      </div>

      <div className="pipeline-branches">
        {SIDE_STEPS.map((step) => (
          <div className="branch-node" key={step}>
            <span>Kafka consumer</span>
            <strong>{step}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}
