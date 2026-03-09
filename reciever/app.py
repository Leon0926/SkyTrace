import connexion
from connexion import NoContent
import json
import datetime
from datetime import datetime
import os
import yaml
import logging.config, logging
import uuid
from pykafka import KafkaClient
import time

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

def connect_to_kafka(max_retries=10, wait_sec=5):
    hostname = app_config['events']['hostname']
    port = app_config['events']['port']
    
    for attempt in range(max_retries):
        try:
            client = KafkaClient(hosts=f'{hostname}:{port}')
            topic = client.topics[str.encode(app_config['events']['topic'])]
            producer = topic.get_sync_producer()
            logger.info("Connected to Kafka successfully")
            return client, producer
        except Exception as e:
            logger.warning(f"Kafka not ready (attempt {attempt+1}/{max_retries}): {e}")
            time.sleep(wait_sec)
    raise Exception("Could not connect to Kafka after max retries")

client, kafka_producer = connect_to_kafka()

def generate_trace_id():
    return str(uuid.uuid4())

def report_aircraft_location(body):
    """ Report aircraft location reading by publishing to Kafka topic """
    trace_id = generate_trace_id()
    body["trace_id"] = trace_id
    reading = body
    msg = { "type": "location_reading",
        "datetime" :
            datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "payload": reading }
    msg_str = json.dumps(msg)
    produce_message(msg_str)
    return NoContent, 201

def report_time_until_arrival(body):
    """ Report aircraft time-until-arrival reading by publishing to Kafka topic """
    trace_id = generate_trace_id()
    body["trace_id"] = trace_id
    reading = body
    msg = { "type": "time_until_arrival_reading",
        "datetime" :
            datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "payload": reading }
    msg_str = json.dumps(msg)
    produce_message(msg_str)
    
    return NoContent, 201

def get_check():
    return NoContent, 200

def produce_message(msg_str):
    """ Publish message to kafka topic with retry logic if fails """
    global client, kafka_producer
    try:
        kafka_producer.produce(msg_str.encode('utf-8'))
    except Exception as e:
        logger.warning(f"Producer disconnected, reconnecting: {e}")
        client, kafka_producer = connect_to_kafka(
            app_config['events']['hostname'],
            app_config['events']['port']
        )
        kafka_producer.produce(msg_str.encode('utf-8'))

app = connexion.FlaskApp(__name__, specification_dir='')
app.add_api("lli249-Aircraft-Readings-1.0.0-resolved.yaml",
            base_path="/reciever",
            strict_validation=True,
            validate_responses=True)

if __name__ == "__main__":
    app.run(host='0.0.0.0',port=8080)
