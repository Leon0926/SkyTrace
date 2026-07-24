# SkyTrace load test runbook

Establishes a sustained-throughput / end-to-end-latency baseline for the
telemetry pipeline: `receiver` (HTTP) → Kafka (`events` topic, 1 partition)
→ `storage` (consumer group `event_group`, persists to MySQL) and
`anomaly_detector` (consumer group `anomaly_group`, threshold checks only).

No new monitoring stack is introduced. Everything here reads from the
Prometheus/Grafana already in `deployment/`: the **Kafka** dashboard
(messages in/out, consumer lag, lag velocity) and the **RED+USE** dashboard
(request rate, HTTP p50/p95, error rate, CPU/mem/OOM — now with two added
panels: **E2E Pipeline Latency (p50/p95/p99)** and **Dead-letter rate**).

## What's instrumented, and why

The load generator stamps every request body with `_lt_sent_ns` (epoch
nanoseconds at send time). This field isn't in the OpenAPI schema, but the
schemas don't forbid extra properties and `receiver/app.py` passes the
whole body through into the Kafka payload unmodified — so it survives the
hop through Kafka for free. `storage/app.py` reads it back out at the
point a message is durably written to MySQL and observes
`now - sent_time` into a new histogram, `skytrace_e2e_latency_seconds`
(buckets from 10ms to 30s), exposed on storage's existing `/metrics`. A
message without the field is completely unaffected — the hook is a no-op.

The measurement point is **storage**, not `anomaly_detector`, even though
both consume the same topic. `storage` persists every message (`anomaly_detector`
only persists the ones that breach a threshold, ~a rare subset), and it's
the one with a dead-letter-style skip in its processing loop
(`skytrace_dead_letter_total`, incremented when a message fails processing
and is skipped but the offset still committed).

**Known landmine, don't trip it:** `anomaly_detector`'s consumer loop has no
try/except, and its anomaly-storage code references `payload['client_id']`,
a field that doesn't exist in the schema (`flight_id` does). If a location
reading's altitude falls outside `[0, 45000]` (or a time-until-arrival's
`time_difference_in_ms` outside `[-300000, 300000]`), that thread crashes
and `anomaly_group` lag will climb for the rest of the run — which looks
like saturation but isn't. The generator keeps synthetic values well
inside those bounds specifically to avoid this. Don't loosen those ranges
without also fixing that bug.

## Prerequisites

- The stack running: `cd deployment && docker compose up -d --build`
- [k6](https://k6.io/) installed locally: `brew install k6` (or
  `docker run --rm -i --network deployment_api.network grafana/k6 run - <script`
  if you'd rather not install it on the host — see note below on `BASE_URL`)
- Grafana at http://localhost:3000, Prometheus at http://localhost:9090

Confirm the pipeline is healthy before loading it:
```
curl -s http://localhost:8080/receiver/check
```

## 1. Run the generator

```
k6 run scripts/loadtest/generate_telemetry.js \
    -e BASE_URL=http://localhost:8080 \
    -e RATE=200 \
    -e RAMP_TIME=30s \
    -e DURATION=3m
```

Key env vars (see comments at the top of the script for the full list):
- `RATE` — target sustained requests/sec (messages/sec, since each request
  is one telemetry event)
- `RAMP_TIME` — time to ramp 0 → RATE (open-loop `ramping-arrival-rate`,
  so offered load doesn't self-throttle under saturation)
- `DURATION` — how long to hold steady at RATE once ramped

If running k6 in a container instead of on the host, set
`BASE_URL=http://receiver:8080` and attach it to the compose network
(`deployment_api.network` by default — check `docker network ls` if the
project directory name differs).

## 2. Find the saturation point

Run at increasing `RATE` (e.g. 100, 200, 500, 1000, 2000...), one run per
rate, watching two dashboards while each run is in progress:

- **Kafka dashboard** → *Messages In* (should track your target rate),
  *Consumer Lag*, *Lag velocity*. The saturation point is the rate at
  which one of these happens:
  - achieved throughput (*Messages In*) visibly falls below target `RATE`, or
  - *Consumer Lag* grows without bound and *Lag velocity* stays
    persistently positive instead of returning to ~0 after the ramp.
- **RED+USE dashboard** → *Request rate* (should also track target rate),
  *p95, p50* (HTTP handling time, receiver-side only), *Error Rate*, *CPU
  Utilization*, *E2E Pipeline Latency*, *Dead-letter rate*.

The last rate where achieved throughput matches target and e2e p95 is
still low/flat is your sustained-throughput ceiling. The next rate up is
where you can characterize degradation (latency blow-up, lag growth, or
errors).

## 3. Read off the numbers

After a run finishes, summarize its steady-state window:

```
python3 scripts/loadtest/summarize_run.py --duration 3m
```

(`--duration` should match/exceed the run's `DURATION` — it sets the
range-vector window for the `rate()`/`histogram_quantile()` queries, and
`increase()` for the dead-letter count.)

This prints: achieved throughput (Kafka messages/sec), receiver HTTP
request rate/error rate, e2e p50/p95/p99, dead-letter count, and final
consumer lag for both `event_group` and `anomaly_group`.

Equivalent PromQL if you'd rather read these off Grafana Explore directly
(all against the Prometheus datasource already provisioned):

```promql
# Achieved throughput
sum(rate(kafka_topic_partition_current_offset{topic="events"}[3m]))

# E2E latency
histogram_quantile(0.50, sum by (le) (rate(skytrace_e2e_latency_seconds_bucket[3m])))
histogram_quantile(0.95, sum by (le) (rate(skytrace_e2e_latency_seconds_bucket[3m])))
histogram_quantile(0.99, sum by (le) (rate(skytrace_e2e_latency_seconds_bucket[3m])))

# Dead-letter count over the run
sum(increase(skytrace_dead_letter_total[3m]))

# Consumer lag right now
sum(kafka_consumergroup_lag{consumergroup="event_group"})
sum(kafka_consumergroup_lag{consumergroup="anomaly_group"})
```

## Notes / caveats

- `_lt_sent_ns` carries millisecond resolution (JS `Date.now()`, padded to
  ns) — negligible against the 10ms–30s range the histogram targets.
- The e2e histogram only observes messages that are *successfully* stored.
  Dead-lettered messages are counted separately (`skytrace_dead_letter_total`)
  and won't appear in the latency distribution — a run with rising
  dead-letter count and flat latency means failures, not slowness.
- The `events` topic has a single partition, so consumption is inherently
  single-threaded per consumer group regardless of rate — that's a
  structural ceiling worth calling out explicitly if you hit it.
- No CI enforcement was added for any of this (this repo currently has no
  pytest suite or GitHub Actions workflow, despite references elsewhere to
  one) — the `storage/app.py` change was kept small and isolated
  (~30 lines, one new import, one new dependency pin) specifically so it's
  easy to review by hand.
