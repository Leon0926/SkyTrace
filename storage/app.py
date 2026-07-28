import connexion
from connexion import NoContent
from sqlalchemy import create_engine, and_, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from create_database import AircraftLocation, ArrivalTime 
from datetime import datetime
import yaml
import logging, logging.config
import json
from pykafka import KafkaClient
from pykafka.common import OffsetType
from threading import Thread, Lock
import os
import time
from prometheus_flask_exporter import PrometheusMetrics
from prometheus_client import Histogram, Counter, REGISTRY

if "TARGET_ENV" in os.environ and os.environ["TARGET_ENV"] == "test":
    print("In Test Environment")
    app_conf_file = "/config/app_conf.yml"
    log_conf_file = "/config/log_conf.yml"
else:
    print("In Dev Environment")
    app_conf_file = "app_conf.yml"
    log_conf_file = "log_conf.yml"

with open(app_conf_file, 'r') as f:
    app_config = yaml.safe_load(f.read())
    
with open(log_conf_file, 'r') as f:
    log_config = yaml.safe_load(f.read())
    logging.config.dictConfig(log_config)
    
logger = logging.getLogger('basicLogger')

logger.info("App Conf File: %s" % app_conf_file)
logger.info("Log Conf File: %s" % log_conf_file)

# --- Load test instrumentation -----------------------------------------
# Optional, non-invasive hook: if a producer stamps a message with
# "_lt_sent_ns" (epoch nanoseconds), we record end-to-end pipeline latency
# here at the point a message is durably stored. Messages without the
# field are unaffected (no schema/behavior change). See scripts/loadtest/.
# Buckets go up to 5m: under saturation, backlogged messages can sit in
# Kafka well past 30s waiting for storage to catch up, and a quantile that
# clips at the top bucket boundary (everything above it collapses into
# +Inf and reports as exactly that boundary) hides how bad the tail
# actually gets.
E2E_LATENCY_BUCKETS = (
    0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75,
    1, 2.5, 5, 7.5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 300,
)


def _get_or_register(collector_cls, name, documentation, **kwargs):
    # connexion resolves each operationId (e.g. "app.get_aircraft_location")
    # by importing this file a second time under the module name "app",
    # separate from the __main__ execution that actually runs app.py and
    # starts the Kafka consumer thread. That reimport re-executes this
    # whole module, including this block, and prometheus_client's default
    # registry is a process-wide singleton -- so the second registration
    # attempt for the same metric name raises ValueError. Reuse the
    # already-registered collector instead of crashing, the same way
    # prometheus_flask_exporter defends against this (see its
    # export_defaults(), which catches ValueError on a re-registration).
    try:
        return collector_cls(name, documentation, **kwargs)
    except ValueError:
        return REGISTRY._names_to_collectors[name]


skytrace_e2e_latency_seconds = _get_or_register(
    Histogram, 'skytrace_e2e_latency_seconds',
    'End-to-end latency from producer send to durable storage in MySQL',
    buckets=E2E_LATENCY_BUCKETS,
)
skytrace_dead_letter_total = _get_or_register(
    Counter, 'skytrace_dead_letter_total',
    'Kafka event messages that failed processing and were skipped (offset still committed)',
)


def _observe_e2e_latency(payload):
    sent_ns = payload.get("_lt_sent_ns")
    if sent_ns is None:
        return
    try:
        latency = time.time() - (float(sent_ns) / 1e9)
    except (TypeError, ValueError):
        return
    if latency >= 0:
        skytrace_e2e_latency_seconds.observe(latency)
# -------------------------------------------------------------------------

user = os.environ.get('MYSQL_USER')
password = os.environ.get('MYSQL_PASSWORD')
hostname = app_config['datastore']['hostname']
port = app_config['datastore']['port']
db = os.environ.get('MYSQL_DATABASE')
DB_ENGINE = create_engine(f'mysql+pymysql://{user}:{password}@{hostname}:{port}/{db}',
                            pool_size=5,
                            pool_recycle=3600,
                            pool_pre_ping=True
                            )

Session = sessionmaker(bind=DB_ENGINE)
consumer_thread = None
consumer_lock = Lock()
KAFKA_RECONNECT_DELAY_SECONDS = 5
# TODO(step 3): move these to app_conf.yml. batch_size=1 reproduces today's
# per-message behavior exactly, which is the baseline for measurement.
BATCH_SIZE = 50
BATCH_FLUSH_TIMEOUT_SECONDS = 2.0

def get_aircraft_location(start_timestamp, end_timestamp):
    """ Get aircraft location readings between start and end timestamps filtered by date_created """
    session = Session()
    start_dt = datetime.fromisoformat(start_timestamp.replace('T', ' '))
    end_dt = datetime.fromisoformat(end_timestamp.replace('T', ' '))

    results = session.query(AircraftLocation).filter(
        and_(
            AircraftLocation.date_created >= start_dt,
            AircraftLocation.date_created <= end_dt))
    results_list = []
    for result in results:
        results_list.append(result.to_dict())

    session.close()
    logger.info("Query for aircraft location readings after %s to %s compared to %s returns %d results", start_timestamp, end_timestamp, AircraftLocation.date_created, len(results_list))
    return results_list, 200

def get_aircraft_time_until_arrival(start_timestamp, end_timestamp):
    """ Get aircraft time-until-arrival readings between start and end timestamps filtered by date_created """
    session = Session()
    
    start_dt = datetime.fromisoformat(start_timestamp.replace('T', ' '))
    end_dt = datetime.fromisoformat(end_timestamp.replace('T', ' '))

    results = session.query(ArrivalTime).filter(
        and_(ArrivalTime.date_created >= start_dt,
             ArrivalTime.date_created <= end_dt))
    
    results_list = []
    for result in results:
        results_list.append(result.to_dict())

    session.close()
    logger.info("Query for aircraft time-until-arrival readings after %s to %s returns %d results", start_timestamp, end_timestamp, len(results_list))
    return results_list, 200

def _insert_row_by_row(session, model_cls, to_insert):
    """Retry a failed batch commit one row at a time so only the actual
    conflicting row(s) get dropped, not the whole batch."""
    stored = []
    for payload, kwargs in to_insert:
        session.add(model_cls(**kwargs))
        try:
            session.commit()
            stored.append((payload, kwargs))
        except IntegrityError:
            session.rollback()
            logger.info('Duplicate trace_id %s hit during row-by-row retry, skipped',
                        kwargs["trace_id"])
    return stored


def _flush_batch(model_cls, pending, kind_label):
    """ Insert every row in `pending` that isn't already stored, in one
        transaction. `pending` is a list of (payload, kwargs) tuples. """
    if not pending:
        return

    trace_ids = [kwargs["trace_id"] for _, kwargs in pending]
    session = Session()
    try:
        existing = {row[0] for row in
                    session.query(model_cls.trace_id)
                           .filter(model_cls.trace_id.in_(trace_ids)).all()}
        to_insert = [(payload, kwargs) for payload, kwargs in pending
                     if kwargs["trace_id"] not in existing]
        skipped = len(pending) - len(to_insert)
        if not to_insert:
            if skipped:
                logger.info('Skipped %d duplicate %s event(s) already stored', skipped, kind_label)
            return

        session.add_all(model_cls(**kwargs) for _, kwargs in to_insert)
        try:
            session.commit()
            stored = to_insert
        except IntegrityError:
            session.rollback()
            stored = _insert_row_by_row(session, model_cls, to_insert)

        for payload, _ in stored:
            _observe_e2e_latency(payload)
        logger.info('Stored %d %s event(s) (%d skipped as duplicates)',
                    len(stored), kind_label, skipped)
    finally:
        session.close()


def process_messages():
    """ Consume events from kafka and persist to MySQL DB in batches
        Runs alongside connexion app as daemon thread"""

    hostname = "%s:%d" % (app_config["events"]["hostname"],
                          app_config["events"]["port"])

    client = None
    while client is None:
        try:
            client = KafkaClient(hosts=hostname)
        except Exception:
            logger.error("Could not connect to Kafka at %s, retrying in %ds",
                         hostname, KAFKA_RECONNECT_DELAY_SECONDS, exc_info=True)
            time.sleep(KAFKA_RECONNECT_DELAY_SECONDS)

    topic = client.topics[str.encode(app_config["events"]["topic"])]
    logger.info(f"Connected to topic: {app_config['events']['topic']}")
    consumer = topic.get_simple_consumer(consumer_group=b'event_group',
                                         reset_offset_on_start=False,
                                         auto_offset_reset=OffsetType.EARLIEST,
                                         consumer_timeout_ms=1000)

    pending_locations = []
    pending_arrivals = []
    batch_start_time = time.time()

    def flush_if_needed():
        nonlocal batch_start_time
        total_pending = len(pending_locations) + len(pending_arrivals)
        if total_pending == 0:
            return
        elapsed = time.time() - batch_start_time
        if total_pending < BATCH_SIZE and elapsed < BATCH_FLUSH_TIMEOUT_SECONDS:
            return

        _flush_batch(AircraftLocation, pending_locations, "location_reading")
        _flush_batch(ArrivalTime, pending_arrivals, "time_until_arrival_reading")
        consumer.commit_offsets()
        pending_locations.clear()
        pending_arrivals.clear()
        batch_start_time = time.time()

    while True:
        for msg in consumer:
            msg_str = msg.value.decode('utf-8')
            try:
                parsed = json.loads(msg_str)
                payload = parsed["payload"]

                if not pending_locations and not pending_arrivals:
                    batch_start_time = time.time()

                if parsed["type"] == "location_reading":
                    pending_locations.append((payload, dict(
                        flight_id=payload["flight_id"],
                        latitude=payload["latitude"],
                        longitude=payload["longitude"],
                        altitude=payload["altitude"],
                        timestamp=datetime.fromisoformat(payload["timestamp"]),
                        date_created=datetime.now(),
                        trace_id=payload["trace_id"]
                    )))
                elif parsed["type"] == "time_until_arrival_reading":
                    pending_arrivals.append((payload, dict(
                        flight_id=payload["flight_id"],
                        estimated_arrival_time=payload["estimated_arrival_time"],
                        actual_arrival_time=payload["actual_arrival_time"],
                        time_difference_in_ms=payload["time_difference_in_ms"],
                        timestamp=datetime.fromisoformat(payload["timestamp"]),
                        date_created=datetime.now(),
                        trace_id=payload["trace_id"]
                    )))
            except Exception:
                logger.error("Failed to process message, skipping: %s", msg_str, exc_info=True)
                skytrace_dead_letter_total.inc()
                continue

            flush_if_needed()

        # consumer_timeout_ms fired (idle) -- still need to check the timeout trigger
        # so a half-full batch under low traffic doesn't sit forever.
        flush_if_needed()

def _consumer_loop():
    """Run process_messages() forever, restarting it if it ever exits or raises."""
    while True:
        try:
            process_messages()
            logger.error("Kafka consumer exited unexpectedly, restarting in %ds",
                         KAFKA_RECONNECT_DELAY_SECONDS)
        except Exception:
            logger.error("Kafka consumer crashed, restarting in %ds",
                         KAFKA_RECONNECT_DELAY_SECONDS, exc_info=True)
        time.sleep(KAFKA_RECONNECT_DELAY_SECONDS)

def start_consumer():
    """Start the Kafka consumer once for this process."""
    global consumer_thread
    with consumer_lock:
        if consumer_thread and consumer_thread.is_alive():
            logger.info("Kafka consumer thread already running")
            return

        consumer_thread = Thread(target=_consumer_loop)
        consumer_thread.daemon = True
        consumer_thread.start()
        logger.info("Kafka consumer thread started")

def get_event_stats():
    """ Get count of each type of event stored in DB """
    session = Session()

    num_location_readings = session.query(AircraftLocation).count()
    num_time_until_arrival_readings = session.query(ArrivalTime).count()

    session.close()

    stats = {
        "num_location_readings": num_location_readings,
        "num_time_until_arrival_readings": num_time_until_arrival_readings
    }

    return stats, 200

app = connexion.FlaskApp(__name__, specification_dir='')
metrics = PrometheusMetrics(app.app)
app.add_api("lli249-Aircraft-Readings-1.0.0-resolved.yaml",
            base_path="/storage",
            strict_validation=True, 
            validate_responses=True)

if __name__ == "__main__":
    logger.info(f"Connecting to DB. Hostname: {app_config['datastore']['hostname']}, Port: {app_config['datastore']['port']}")

    start_consumer()
    app.run(host='0.0.0.0',port=8090)
    
    
