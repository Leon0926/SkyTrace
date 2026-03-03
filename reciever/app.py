import connexion
from connexion import NoContent
import json
import datetime
from datetime import datetime
import os
import requests
import yaml
import logging.config, logging
import uuid
from pykafka import KafkaClient

DATA_STORAGE_URL="http://localhost:8090/readings"

def generate_trace_id():
    return str(uuid.uuid4())

def report_aircraft_location(body):
    event_name = "location"
    trace_id = generate_trace_id()
    body["trace_id"] = trace_id
    reading = body
    kafak_topic = client.topics[str.encode(app_config['events']['topic'])]
    #producer = kafka_topic.get_sync_producer()
    msg = { "type": "location_reading",
        "datetime" :
            datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "payload": reading }
    msg_str = json.dumps(msg)
    kafka_producer.produce(msg_str.encode('utf-8'))
    return NoContent, 201

def report_time_until_arrival(body):
    
    event_name = "time_until_arrival"
    trace_id = generate_trace_id()
    body["trace_id"] = trace_id
    reading = body
    kafka_topic = client.topics[str.encode(app_config['events']['topic'])]
    #producer = kafka_topic.get_sync_producer()
    msg = { "type": "time_until_arrival_reading",
        "datetime" :
            datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "payload": reading }
    msg_str = json.dumps(msg)
    kafka_producer.produce(msg_str.encode('utf-8'))
    
    return NoContent, 201

def get_check():
    return NoContent, 200

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


hostname = app_config['events']['hostname']
port = app_config['events']['port']
client = KafkaClient(hosts=f'{hostname}:{port}')

kafka_topic = client.topics[str.encode(app_config['events']['topic'])]
kafka_producer = kafka_topic.get_sync_producer()

app = connexion.FlaskApp(__name__, specification_dir='')
app.add_api("lli249-Aircraft-Readings-1.0.0-resolved.yaml",
            base_path="/reciever",
            strict_validation=True,
            validate_responses=True)

if __name__ == "__main__":
    app.run(host='0.0.0.0',port=8080)
