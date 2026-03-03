import connexion
from connexion import NoContent
import json
import datetime
from datetime import datetime
import yaml
import logging.config, logging
from pykafka import KafkaClient
from collections import defaultdict
from flask import jsonify
from connexion import FlaskApp
from connexion.middleware import MiddlewarePosition
from starlette.middleware.cors import CORSMiddleware
from contextlib import contextmanager
import os

@contextmanager
def get_kafka_consumer(hostname, topic_name):
    """Context manager for safely handling Kafka consumer lifecycle"""
    client = KafkaClient(hosts=hostname)
    topic = client.topics[str.encode(topic_name)]
    consumer = topic.get_simple_consumer(
        reset_offset_on_start=True,
        consumer_timeout_ms=1000,
        auto_commit_enable=True
    )
    try:
        yield consumer
    finally:
        if consumer:
            try:
                consumer.commit_offsets()
                consumer.stop()
            except Exception as e:
                logger.error(f"Error cleaning up consumer: {str(e)}")

app = connexion.FlaskApp(__name__, specification_dir='')
app.add_api("lli249-Aircraft_readings-1.0.0-resolved.yaml",
            base_path="/analyzer",
            strict_validation=True,
            validate_responses=True)

app.add_middleware(
    CORSMiddleware,
    position=MiddlewarePosition.BEFORE_EXCEPTION,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if "TARGET_ENV" not in os.environ or os.environ["TARGET_ENV"] != "test":
    CORS(app.app)
    app.app.config['CORS_HEADERS'] = 'Content-Type'

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


def get_aircraft_location_reading(index):
    """ Get location Reading in History """
    hostname = "%s:%d" % (app_config["events"]["hostname"], app_config["events"]["port"])
    
    try:
        with get_kafka_consumer(hostname, app_config["events"]["topic"]) as consumer:
            logger.info("Retrieving location at index %d" % index)
            current_index = 0
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    for msg in consumer:
                        if msg is None:
                            continue
                            
                        try:
                            msg_str = msg.value.decode('utf-8')
                            msg = json.loads(msg_str)
                            
                            if msg.get("type") == "location_reading":
                                if current_index == index:
                                    event = msg.get("payload")
                                    if event:
                                        logger.info("Found location reading at index %d" % index)
                                        return event, 200
                                current_index += 1
                                
                        except json.JSONDecodeError as e:
                            logger.error(f"Error decoding message: {str(e)}")
                            continue
                    break  
                    
                except Exception as e:
                    logger.error(f"Error reading messages (attempt {retry_count + 1}): {str(e)}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        return {"message": "Error reading messages"}, 500
                    continue
                    
    except Exception as e:
        logger.error(f"Error connecting to Kafka: {str(e)}")
        return {"message": "Error connecting to message broker"}, 500

    logger.error(f"Could not find location reading at index {index}. Max index reached: {current_index}")
    return {"message": f"Not Found. Max index available: {current_index}"}, 404

def get_aircraft_time_until_arrival_reading(index):
    """ Get time-until-arrival Reading in History """
    hostname = "%s:%d" % (app_config["events"]["hostname"], app_config["events"]["port"])
    
    try:
        with get_kafka_consumer(hostname, app_config["events"]["topic"]) as consumer:
            logger.info("Retrieving time-until-arrival at index %d" % index)
            current_index = 0
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    for msg in consumer:
                        if msg is None:
                            continue
                            
                        try:
                            msg_str = msg.value.decode('utf-8')
                            msg = json.loads(msg_str)
                            
                            if msg.get("type") == "time_until_arrival_reading":
                                if current_index == index:
                                    event = msg.get("payload")
                                    if event:
                                        logger.info("Found time-until-arrival reading at index %d" % index)
                                        return event, 200
                                current_index += 1
                                
                        except json.JSONDecodeError as e:
                            logger.error(f"Error decoding message: {str(e)}")
                            continue
                    break  
                    
                except Exception as e:
                    logger.error(f"Error reading messages (attempt {retry_count + 1}): {str(e)}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        return {"message": "Error reading messages"}, 500
                    continue
                    
    except Exception as e:
        logger.error(f"Error connecting to Kafka: {str(e)}")
        return {"message": "Error connecting to message broker"}, 500

    logger.error(f"Could not find time-until-arrival reading at index {index}. Max index reached: {current_index}")
    return {"message": f"Not Found. Max index available: {current_index}"}, 404

def get_event_stats():
    hostname = "%s:%d" % (app_config["events"]["hostname"], app_config["events"]["port"])
    
    try:
        with get_kafka_consumer(hostname, app_config["events"]["topic"]) as consumer:
            event_counts = defaultdict(int)
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    for msg in consumer:
                        if msg is None:
                            continue
                            
                        try:
                            msg_str = msg.value.decode('utf-8')
                            msg = json.loads(msg_str)
                            
                            event_type = msg.get("type")
                            if event_type:
                                event_counts[event_type] += 1
                                
                        except json.JSONDecodeError as e:
                            logger.error(f"Error decoding message: {str(e)}")
                            continue
                    break  # If we get here successfully, break the retry loop
                    
                except Exception as e:
                    logger.error(f"Error reading messages (attempt {retry_count + 1}): {str(e)}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        return {"message": "Error reading messages"}, 500
                    continue

            logger.info("Successfully retrieved event type stats")
            return jsonify(event_counts), 200
            
    except Exception as e:
        logger.error(f"Error connecting to Kafka: {str(e)}")
        return {"message": "Error connecting to message broker"}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8110)