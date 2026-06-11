import React, { useCallback, useEffect, useState } from "react";
import logo from "./logo.png";
import "./App.css";

import {
  fetchAnalyzerStats,
  fetchAnomalies,
  fetchHealth,
  fetchStats
} from "./api";
import AnomalyFeed from "./components/AnomalyFeed";
import PipelineView from "./components/PipelineView";
import ServiceHealth from "./components/ServiceHealth";
import SystemActivity from "./components/SystemActivity";
import TelemetryStats from "./components/TelemetryStats";

const EMPTY_ERRORS = {
  stats: null,
  health: null,
  analyzer: null,
  anomalies: null
};

function App() {
  const [stats, setStats] = useState({});
  const [health, setHealth] = useState({});
  const [analyzerStats, setAnalyzerStats] = useState({});
  const [anomalies, setAnomalies] = useState([]);
  const [errors, setErrors] = useState(EMPTY_ERRORS);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadDashboardData = useCallback(async () => {
    const nextErrors = { ...EMPTY_ERRORS };

    const [statsResult, healthResult, analyzerResult, anomaliesResult] =
      await Promise.allSettled([
        fetchStats(),
        fetchHealth(),
        fetchAnalyzerStats(),
        fetchAnomalies()
      ]);

    if (statsResult.status === "fulfilled") {
      setStats(statsResult.value);
    } else {
      nextErrors.stats = statsResult.reason;
    }

    if (healthResult.status === "fulfilled") {
      setHealth(healthResult.value);
    } else {
      nextErrors.health = healthResult.reason;
    }

    if (analyzerResult.status === "fulfilled") {
      setAnalyzerStats(analyzerResult.value);
    } else {
      nextErrors.analyzer = analyzerResult.reason;
    }

    if (anomaliesResult.status === "fulfilled") {
      setAnomalies(anomaliesResult.value);
    } else {
      nextErrors.anomalies = anomaliesResult.reason;
    }

    setErrors(nextErrors);
    setLastRefresh(new Date());
    setIsLoading(false);
  }, []);

  useEffect(() => {
    loadDashboardData();
    const interval = setInterval(loadDashboardData, 3000);
    return () => clearInterval(interval);
  }, [loadDashboardData]);

  return (
    <div className="dashboard-shell">
      <header className="topbar">
        <div className="brand">
          <img src={logo} alt="SkyTrace" />
          <div>
            <p className="eyebrow">Aircraft telemetry</p>
            <h1>SkyTrace Control Center</h1>
          </div>
        </div>
        <div className="refresh-card">
          <span>Refresh</span>
          <strong>{isLoading ? "Loading" : "3s live"}</strong>
        </div>
      </header>

      <main>
        <TelemetryStats stats={stats} analyzerStats={analyzerStats} />

        <div className="dashboard-grid">
          <ServiceHealth health={health} error={errors.health} />
          <SystemActivity
            stats={stats}
            analyzerStats={analyzerStats}
            lastRefresh={lastRefresh}
            errors={errors}
          />
        </div>

        <PipelineView />

        <AnomalyFeed anomalies={anomalies} error={errors.anomalies} />
      </main>
    </div>
  );
}

export default App;
