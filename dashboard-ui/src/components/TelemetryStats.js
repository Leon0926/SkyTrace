import React from "react";

function formatNumber(value) {
  if (value === undefined || value === null || value === "") {
    return "0";
  }

  return Number(value).toLocaleString();
}

export default function TelemetryStats({ stats, analyzerStats }) {
  const cards = [
    {
      label: "Location Events",
      value: formatNumber(stats.num_location_readings),
      note: `${formatNumber(analyzerStats.location_reading)} in Kafka`
    },
    {
      label: "ETA Events",
      value: formatNumber(stats.num_time_until_arrival_readings),
      note: `${formatNumber(analyzerStats.time_until_arrival_reading)} in Kafka`
    },
    {
      label: "Max Latitude",
      value: formatNumber(stats.max_location_latitude_reading),
      note: "Highest processed latitude"
    },
    {
      label: "Max ETA Drift",
      value: `${formatNumber(stats.max_time_until_arrival_time_difference_in_ms_reading)} ms`,
      note: "Largest arrival delta"
    }
  ];

  return (
    <section className="metrics-grid" aria-label="Telemetry statistics">
      {cards.map((card) => (
        <article className="metric-card" key={card.label}>
          <p>{card.label}</p>
          <strong>{card.value}</strong>
          <span>{card.note}</span>
        </article>
      ))}
    </section>
  );
}
