const API_BASE = process.env.REACT_APP_API_BASE || "";

async function requestJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`);

  if (options.emptyOnNotFound && response.status === 404) {
    return options.emptyValue;
  }

  if (!response.ok) {
    throw new Error(`Request failed for ${path}: ${response.status}`);
  }

  return response.json();
}

export function fetchStats() {
  return requestJson("/processing/stats");
}

export function fetchHealth() {
  return requestJson("/check/check");
}

export function fetchAnalyzerStats() {
  return requestJson("/analyzer/stats");
}

export function fetchAnomalies() {
  return requestJson("/anomaly_detector/anomalies", {
    emptyOnNotFound: true,
    emptyValue: []
  });
}
