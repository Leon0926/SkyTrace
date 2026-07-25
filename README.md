## Description

Distributed aircraft telemetry system built with Python microservices, Kafka, MySQL. Containerized with Docker Compose, routed with Nginx, monitored with Prometheus/Grafana.
Includes: <br>

• Microservice Architecture  • Async Messaging  • Event Sourcing • Observability (Health Check, Prometheus/Grafana) <br>
• Containerization + Orchestration  • RESTful API Design • Reverse Proxy + Load Balancing • Load Testing (k6)

<img width="1869" height="887" alt="image" src="https://github.com/user-attachments/assets/c81e6e83-832c-412f-83e7-29c5554e9fbd" />

## Architecture Summary (More details below)

6 independent services communicate through a shared Kafka topic and over the Docker network, backed by a Prometheus/Grafana monitoring stack

**Receiver** — Public-facing edge service that ingests aircraft telemetry via REST, validates payloads, and publishes to Kafka. 

**Storage** — Consumes Kafka events and persists to MySQL. Also exposes a time-range query API.

**Processing** — Polls Storage periodically, computes running aggregate stats (event counts, max values), and caches results to disk.

**Analyzer** — Read-only Kafka consumer. Look up any event by queue index or get a count of events per type. 

**Anomaly Detector** — Consumes Kafka events and flags readings that breach configurable thresholds. Persists anomalies to local JSON file.

**Health Check** — Single endpoint that polls all services routinely and writes a live status snapshot. 

**Monitoring** — Prometheus scrapes every service plus cAdvisor (container resource usage), mysqld-exporter (MySQL), and kafka-exporter/JMX exporter (broker health, consumer lag). Grafana dashboards cover RED+USE metrics and Kafka throughput/lag.

## Running Locally

**Prerequisites:** Docker, Docker Compose

```bash
git clone https://github.com/leon0926/skytrace
cd skytrace/deployment
cp .env.example .env      # fill in DB_PASSWORD
docker compose up --build
```

Grafana at `localhost:3000`, Prometheus at `localhost:9090`.

## Service details/notes

| Service | Details | 
|---------|---------|
| All Services |  • Centralized app and log config <br> • OpenAPI spec per service | 
| Receiver |   • Edge service; communicates with public <br> • Takes in aircraft telemetry data via REST <br> • OpenAPI spec validation via Connexion, rejects invalid requests before reaching funcs <br> • 2 POST endpoints: location (coordinates, altitude) and time-until-arrival (estimated time until arrival, actual time until arrival, time difference in ms) <br> • Connects to Kafka with 10 retry attempts, 5 sec apart <br> • Appends traceID and datetime to payload <br> • publishes all msgs to Kafka topic/queue | 
| Storage |  • persists kafka events to MySQL and exposes endpoints for other services <br> • creates connection to MySQL using SQLAlchemy (ORM)  <br> • Reads db name, user, password from env vars <br> • 2 GET endpoints that fetch stored events between 2 timestamps <br> • runs a Kafka consumer on a daemon thread; reset_offset_on_start=False prevents loss/replay via last committed offset <br> • self-healing: consumer loop is wrapped and auto-restarts on crash/disconnect; a failed message is logged to a dead-letter counter and skipped (not retried) so one bad payload can't stall the offset <br> • observes end-to-end pipeline latency (send → persisted) for the load-testing metrics below <br> • 1 GET endpoint that fetch counts for each db table <br> • must manually run create_tables.py and drop_tables.py to create/destroy db | 
| Processing |   • pulls from storage service and serves aggregate stats to dashboard<br> • calls storage GET endpoint periodically, writes/updates the following to local json: <br>&nbsp; • # of location readings<br>&nbsp; • max altitude reading<br>&nbsp; • # of time-until-arrival readings<br>&nbsp; • max time-until-arrival-difference-in-ms reading<br> • 1 GET endpoint to fetch stats from persisted local json<br> • Uses APScheduler to run every N seconds in background thread, dies with main app<br> • CORS allows dashboard to make requests despite running in browser | 
| Analyzer |   • reads from Kafka to get events by index # or counts of event type<br> • 2 GET endpoint that returns event in kafka topic given index<br> • 1 GET endpoint that returns count of each event in kafka topic<br> • creates fresh consumer and cleans up per request (not persistent, more expensive)<br> • CORS for dashboard | 
| Anomaly Detector |   • reads + writes detected event anomalies to flat, persistent local json<br> • anomalies defined as being outside given range of values defined in app_config<br> • 1 GET endpoint that returns anomalies; can be filtered by above/under thresholds<br> • reads from events topic under anomaly_group (diff from other events_group)<br> • runs async on daemon thread like storage | 
| Health Check |   • pings every service and creates status report<br> • catches timeout and connection errors, writing status to local persistent json<br> • service url + timeout stored in app_config<br> • 1 GET endpoint to read status json <br> • runs async on daemon thread every N seconds (defined in config) | 
| Dashboard | • React SPA that displays live aircraft telemetry data, auto refreshing<br> • polls processing service every 2 sec for aggregate stats<br> • polls analyzer service every 4 sec and fetch random event by index | 
| Monitoring | • Prometheus scrapes all services' `/metrics`, plus cAdvisor, mysqld-exporter, kafka-exporter, and Kafka's JMX exporter<br> • Grafana dashboards provisioned on startup: RED+USE (request rate, latency, errors, CPU/mem) and Kafka (throughput, consumer lag)<br> • storage exposes `skytrace_e2e_latency_seconds` and `skytrace_dead_letter_total` for pipeline-level latency/failure tracking | 
| Load Testing | • k6 script (`scripts/loadtest`) drives sustained request rates at receiver to find the pipeline's throughput ceiling<br> • `summarize_run.py` reads Prometheus after a run for throughput, e2e p50/p95/p99, dead-letter count, and consumer lag<br> • see `scripts/loadtest/README.md` for the full runbook | 
