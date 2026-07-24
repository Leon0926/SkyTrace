#!/usr/bin/env python3
"""Summarize a SkyTrace load test run by querying Prometheus directly.

Computes, over a given window ending now (or ending at --end):
  - achieved throughput (messages/sec actually landed in Kafka)
  - end-to-end pipeline latency p50 / p95 / p99 (storage sink)
  - dead-letter count (messages skipped by storage)
  - final consumer lag for both consumer groups (storage, anomaly_detector)

Run this right after a k6 run finishes, with --duration matching (or
slightly exceeding) how long the run held steady state, so the range
vectors used for the histogram_quantile / rate() queries cover the run.

Usage:
    python3 scripts/loadtest/summarize_run.py --duration 2m
    python3 scripts/loadtest/summarize_run.py --duration 5m --prometheus-url http://localhost:9090
"""

import argparse
import sys
from datetime import datetime, timezone

import requests

TOPIC = "events"
STORAGE_GROUP = "event_group"
ANOMALY_GROUP = "anomaly_group"


def query(prom_url, expr, time=None):
    params = {"query": expr}
    if time is not None:
        params["time"] = time
    resp = requests.get(f"{prom_url}/api/v1/query", params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data["status"] != "success":
        raise RuntimeError(f"Prometheus query failed: {data}")
    return data["data"]["result"]


def scalar(prom_url, expr, time=None, default=None):
    result = query(prom_url, expr, time=time)
    if not result:
        return default
    return float(result[0]["value"][1])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prometheus-url", default="http://localhost:9090", help="Prometheus base URL")
    parser.add_argument("--duration", default="2m", help="Steady-state window to summarize, e.g. 2m, 90s (should match/exceed the run's hold duration)")
    args = parser.parse_args()

    prom_url = args.prometheus_url.rstrip("/")
    d = args.duration

    print(f"SkyTrace load test summary — window: last {d}, evaluated at {datetime.now(timezone.utc).isoformat()}")
    print("=" * 72)

    throughput = scalar(prom_url, f'sum(rate(kafka_topic_partition_current_offset{{topic="{TOPIC}"}}[{d}]))', default=0.0)
    print(f"Achieved throughput (Kafka in):     {throughput:8.2f} msg/sec")

    receiver_rate = scalar(prom_url, f'sum(rate(flask_http_request_total{{job="receiver"}}[{d}]))', default=0.0)
    receiver_errors = scalar(prom_url, f'sum(rate(flask_http_request_total{{job="receiver",status=~"5.."}}[{d}]))', default=0.0)
    err_pct = (receiver_errors / receiver_rate * 100) if receiver_rate else 0.0
    print(f"Receiver HTTP request rate:         {receiver_rate:8.2f} req/sec  (error rate: {err_pct:.2f}%)")

    print()
    print("End-to-end pipeline latency (producer send -> stored in MySQL):")
    for q, label in ((0.50, "p50"), (0.95, "p95"), (0.99, "p99")):
        expr = f"histogram_quantile({q}, sum by (le) (rate(skytrace_e2e_latency_seconds_bucket[{d}])))"
        val = scalar(prom_url, expr)
        val_str = f"{val * 1000:8.1f} ms" if val is not None else "     n/a (no samples in window)"
        print(f"  {label}: {val_str}")

    print()
    dead_letters = scalar(prom_url, f"sum(increase(skytrace_dead_letter_total[{d}]))", default=0.0)
    print(f"Dead-lettered messages (storage skip): {dead_letters:.0f}")

    print()
    print("Consumer lag (instantaneous, at evaluation time):")
    for group in (STORAGE_GROUP, ANOMALY_GROUP):
        lag = scalar(prom_url, f'sum(kafka_consumergroup_lag{{consumergroup="{group}"}})', default=None)
        lag_str = f"{lag:.0f}" if lag is not None else "n/a"
        print(f"  {group:20s}: {lag_str}")

    print()
    print("Reminder: saturation = achieved throughput falling below target rate,")
    print("or consumer lag growing unboundedly. Check the Kafka dashboard's")
    print("'Lag velocity' panel — sustained positive slope means the pipeline")
    print("can't keep up at this rate.")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as e:
        print(f"Error querying Prometheus: {e}", file=sys.stderr)
        sys.exit(1)
