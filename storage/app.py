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
from threading import Thread
import os

#engine = create_engine('sqlite:///events.db')

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

user = app_config['datastore']['user']
password = app_config['datastore']['password']
hostname = app_config['datastore']['hostname']
port = app_config['datastore']['port']
db = app_config['datastore']['db']

DB_ENGINE = create_engine(f'mysql+pymysql://{user}:{password}@{hostname}:{port}/{db}',
                            pool_size=5,
                            pool_recycle=3600,
                            pool_pre_ping=True
                            )

#DB_ENGINE = create_engine(f'mysql+pymysql://{app_config['datastore']['user']}:{app_config['datastore']['password']}@{app_config['datastore']['hostname']}:{app_config['datastore']['port']}/{app_config['datastore']['db']}')
Session = sessionmaker(bind=DB_ENGINE)

""" def report_aircraft_location(body):
    event_name = "location"

    session = Session()
    
    new_location_event = AircraftLocation(
        flight_id=body["flight_id"],
        latitude=body["latitude"],
        longitude=body["longitude"],
        timestamp=datetime.fromisoformat(body["timestamp"]),
        date_created=datetime.now(),
        trace_id=body["trace_id"]
       
    )
    
    session.add(new_location_event)
    session.commit()
    logger.info(f'Stored event {event_name} request with a trace id of {body["trace_id"]}')
    session.close()
    return NoContent, 201

def report_time_until_arrival(body):
    event_name = "time_until_arrival"
    
    session = Session()
    new_arrival_event = ArrivalTime(
        flight_id=body["flight_id"],
        estimated_arrival_time=body["estimated_arrival_time"],
        actual_arrival_time=body["actual_arrival_time"],
        time_difference_in_ms=body["time_difference_in_ms"],
        timestamp=datetime.fromisoformat(body["timestamp"]),
        date_created=datetime.now(),
        trace_id=body["trace_id"]
    )
    session.add(new_arrival_event)
    session.commit()
    logger.info(f'Stored event {event_name} request with a trace id of {body["trace_id"]}')
    session.close()
    return NoContent, 201 """

def get_aircraft_location(start_timestamp, end_timestamp):
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
    return results_list, 201

def get_aircraft_time_until_arrival(start_timestamp, end_timestamp):
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
    return results_list, 201

def debug_aircraft_location():
    session = Session()
    results = session.query(AircraftLocation).all()
    for result in results:
        logger.debug(f"AircraftLocation.date_created: {result.date_created}")
    session.close()

def process_messages():
    """ Process event messages """
    hostname = "%s:%d" % (app_config["events"]["hostname"],
                          app_config["events"]["port"])
        
    client = KafkaClient(hosts=hostname)
    topic = client.topics[str.encode(app_config["events"]["topic"])]
    logger.info(f"Connected to topic: {app_config['events']['topic']}")
    # Create a consume on a consumer group, that only reads new messages
    # (uncommitted messages) when the service re-starts (i.e., it doesn't
    # read all the old messages from the history in the message queue).
    consumer = topic.get_simple_consumer(consumer_group=b'event_group',
                                         reset_offset_on_start=False,
                                         auto_offset_reset=OffsetType.EARLIEST)
    # This is blocking - it will wait for a new message
    for msg in consumer:
        msg_str = msg.value.decode('utf-8')
        msg = json.loads(msg_str)
        logger.info("Message: %s" % msg)
        payload = msg["payload"]
        if msg["type"] == "location_reading": # Change this to your event type
            # Store the event1 (i.e., the payload) to the DB
            session = Session()
            new_location_event = AircraftLocation(
                flight_id=payload["flight_id"],
                latitude=payload["latitude"],
                longitude=payload["longitude"],
                timestamp=datetime.fromisoformat(payload["timestamp"]),
                date_created=datetime.now(),
                trace_id=payload["trace_id"]
            )
            session.add(new_location_event)
            session.commit()
            logger.info(f'Stored event {msg["type"]} request with a trace id of {payload["trace_id"]}')
            session.close()

        elif msg["type"] == "time_until_arrival_reading": # Change this to your event type
            # Store the event2 (i.e., the payload) to the DB
            session = Session()
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
            session.close()
        # Commit the new message as being read
        consumer.commit_offsets()

def get_event_stats():
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
app.add_api("lli249-Aircraft-Readings-1.0.0-resolved.yaml", 
            base_path="/storage",
            strict_validation=True, 
            validate_responses=True)

if __name__ == "__main__":
    #debug_aircraft_location()
    logger.info(f"Connecting to DB. Hostname: {app_config['datastore']['hostname']}, Port: {app_config['datastore']['port']}")

    t1 = Thread(target=process_messages)
    t1.setDaemon(True)
    t1.start()

    app.run(host='0.0.0.0',port=8090)
    
    
