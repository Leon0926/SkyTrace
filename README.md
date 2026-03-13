## Description

Distributed aircraft telementry pipeline built with Python microservices, Kafka, MySQL. Containerized with Docker Compose, routed with Nginx.

## Architecture

6 independent services communicate through a shared Kafka topic and over Docker network

**Receiver** — Edge service that ingests aircraft telemetry via REST, validates payloads, and publishes to Kafka. The only public-facing write endpoint in the system.

**Storage** — Consumes Kafka events and persists to MySQL. Also exposes a time-range query API.

**Processing** — Polls Storage on a configurable schedule, computes running aggregate stats (event counts, max values), and caches results to disk. State persists across restarts.

**Analyzer** — Read-only Kafka consumer. Look up any event by queue index or get a count of events per type.

**Anomaly Detector** — Consumes Kafka events and flags readings that breach configurable thresholds (too high / too low). Persists anomalies to a local JSON store.

**Health Check** — Single endpoint that polls all services routinely and writes a live status snapshot. 

### ADD IMAGE HERE

## Running Locally

**Prerequisites:** Docker, Docker Compose

```bash
git clone https://github.com/leon0926/skytrace
cd skytrace/deployment
cp .env.example .env      # fill in DB_PASSWORD
docker compose up --build
```

## Configuration

Each service reads from its own `app_conf.yml`. Sensitive values are inserted through environment variables. Required variables show in `.env.example`.
