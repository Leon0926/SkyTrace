import connexion
from connexion import NoContent
from sqlalchemy import create_engine, and_, func
from sqlalchemy.orm import sessionmaker
from create_database import AircraftLocation, ArrivalTime 
from datetime import datetime
import yaml
import logging, logging.config
import json
from pykafka import KafkaClient
from pykafka.common import OffsetType
from threading import Thread, Lock
import os
from prometheus_flask_exporter import PrometheusMetrics

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

def process_messages():
    """ Consume events from kafka and persist to MySQL DB
        Runs alongside connexion app as daemon thread"""
    
    hostname = "%s:%d" % (app_config["events"]["hostname"],
                          app_config["events"]["port"])
        
    client = KafkaClient(hosts=hostname)
    topic = client.topics[str.encode(app_config["events"]["topic"])]
    logger.info(f"Connected to topic: {app_config['events']['topic']}")
    consumer = topic.get_simple_consumer(consumer_group=b'event_group',
                                         reset_offset_on_start=False,
                                         auto_offset_reset=OffsetType.EARLIEST)
    for msg in consumer:
        msg_str = msg.value.decode('utf-8')
        msg = json.loads(msg_str)
        logger.info("Message: %s" % msg)
        payload = msg["payload"]
        if msg["type"] == "location_reading": 
            session = Session()
            try:
                existing_event = session.query(AircraftLocation).filter(
                    AircraftLocation.trace_id == payload["trace_id"]
                ).first()
                if existing_event:
                    logger.info('Duplicate event %s with trace id %s skipped', msg["type"], payload["trace_id"])
                else:
                    new_location_event = AircraftLocation(
                        flight_id=payload["flight_id"],
                        latitude=payload["latitude"],
                        longitude=payload["longitude"],
                        altitude=payload["altitude"],
                        timestamp=datetime.fromisoformat(payload["timestamp"]),
                        date_created=datetime.now(),
                        trace_id=payload["trace_id"]
                    )
                    session.add(new_location_event)
                    session.commit()
                    logger.info(f'Stored event {msg["type"]} request with a trace id of {payload["trace_id"]}')
            finally:
                session.close()

        elif msg["type"] == "time_until_arrival_reading":
            session = Session()
            try:
                existing_event = session.query(ArrivalTime).filter(
                    ArrivalTime.trace_id == payload["trace_id"]
                ).first()
                if existing_event:
                    logger.info('Duplicate event %s with trace id %s skipped', msg["type"], payload["trace_id"])
                else:
                    new_arrival_event = ArrivalTime(
                        flight_id=payload["flight_id"],
                        estimated_arrival_time=payload["estimated_arrival_time"],
                        actual_arrival_time=payload["actual_arrival_time"],
                        time_difference_in_ms=payload["time_difference_in_ms"],
                        timestamp=datetime.fromisoformat(payload["timestamp"]),
                        date_created=datetime.now(),
                        trace_id=payload["trace_id"]
                    )
                    session.add(new_arrival_event)
                    session.commit()
                    logger.info(f'Stored event {msg["type"]} request with a trace id of {payload["trace_id"]}')
            finally:
                session.close()

        consumer.commit_offsets()

def start_consumer():
    """Start the Kafka consumer once for this process."""
    global consumer_thread
    with consumer_lock:
        if consumer_thread and consumer_thread.is_alive():
            logger.info("Kafka consumer thread already running")
            return

        consumer_thread = Thread(target=process_messages)
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
    
    
