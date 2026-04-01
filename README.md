## Description

Distributed aircraft telementry system built with Python microservices, Kafka, MySQL. Containerized with Docker Compose, routed with Nginx.
Includes: <br>

• Microservice Architecture  • Async Messaging  • Event Sourcing • Observability - Health Check + Dashboard <br>
• Containerization + Orchestration  • RESTful API Design • Reverse Proxy + Load Balancing 

<img width="1869" height="887" alt="image" src="https://github.com/user-attachments/assets/c81e6e83-832c-412f-83e7-29c5554e9fbd" />

## Architecture Summary (More details below)

6 independent services communicate through a shared Kafka topic and over Docker network

**Receiver** — Public-facing edge service that ingests aircraft telemetry via REST, validates payloads, and publishes to Kafka. 

**Storage** — Consumes Kafka events and persists to MySQL. Also exposes a time-range query API.

**Processing** — Polls Storage periodically, computes running aggregate stats (event counts, max values), and caches results to disk.

**Analyzer** — Read-only Kafka consumer. Look up any event by queue index or get a count of events per type. 

**Anomaly Detector** — Consumes Kafka events and flags readings that breach configurable thresholds. Persists anomalies to local JSON file.

**Health Check** — Single endpoint that polls all services routinely and writes a live status snapshot. 

## Running Locally

**Prerequisites:** Docker, Docker Compose

```bash
git clone https://github.com/leon0926/skytrace
cd skytrace/deployment
cp .env.example .env      # fill in DB_PASSWORD
docker compose up --build
```

## Service details/notes

| Service | Details | 
|---------|---------|
| All Services |  • Centralized app and log config <br> • OpenAPI spec per service | 
| Receiver |   • Edge service; communicates with public <br> • Takes in aircraft telemetry data via REST <br> • OpenAPI spec validation via Connexion, rejects invalid requests before reaching funcs <br> • 2 POST endpoints: location (coordinates, altitude) and time-until-arrival (estimated time until arrival, actual time until arrrival, time difference in ms) <br> • Connects to Kafka with 10 retry attempts, 5 sec inbetween <br> • Appends traceID and datetime to payload <br> • publish all msgs to Kafka topic/queue | 
| Storage |  • persists kafka events to MySQL and exposes endpoints for other services <br> • creates connection to MySQL using SQLAlchemy (ORM)  <br> • Reads db name, user, password from env vars <br> • 2 GET endpoints that fetch stored events between 2 timestamps <br> • creates kafka consumer that runs as daemon thread (async); reads msg from topic<br> • routes and adds msgs to correct db table<br> • reset_offset_on_start=False prevents loss/replay of msgs via last commited offset<br> • 1 GET endpoint that fetch counts for each db table <br> • must manually run create_tables.py and drop_tables.py to create/destroy db | 
| Processing |   • pulls from storage service and serves aggregate stats to dashboard<br> • calls storage GET endpoint periodically, writes/updates the following to local json: <br>&nbsp; • # of location readings<br>&nbsp; • max altitude reading<br>&nbsp; • # of time-until-arrival readings<br>&nbsp; • max time-until-arrival-difference-in-ms reading<br> • 1 GET endpoint to fetch stats from persisted local json<br> • Uses APScheduler to run every N seconds in background thread, dies with main app<br> • CORS allows dashboard to make requests despite running in browser | 
| Analyzer |   • reads from Kafka to get events by index # or counts of event type<br> • 2 GET endpoint that returns event in kafka topic given index<br> • 1 GET endpoint that returns count of each event in kafka topic<br> • creates fresh consumer and cleans up per request (not persistent, more expensive)<br> • CORS for dashboard | 
| Anomaly Detector |   • reads + writes detected event anomalies to flat, persistent local json<br> • anomalies defined as being outside given range of values defined in app_config<br> • 1 GET endpoint that returns anomalies; can be filtered by above/under threshholds<br> • reads from events topic under anomaly_group (diff from other events_group)<br> • runs async on daemon thread like storage | 
| Health Check |   • pings every service and creates status report<br> • catches timeout and connection errors, writing status to local persistent json<br> • service url + timeout stored in app_config<br> • 1 GET endpoint to read status json <br> • runs async on daemon thread even N seconds (defined in config) | 
| Dashboard | • React SPA that displays live aircraft telemtry data, auto refreshing<br> • polls processing service every 2 sec for aggregate stats<br> • polls analyzer service every 4 sec and fetch random event by index | 
