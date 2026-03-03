import connexion
import json
import datetime
import logging
import logging.config
import yaml
import uuid
from pykafka import KafkaClient
from pykafka.common import OffsetType
import os
import time
from threading import Thread

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

def store_anomaly(anomaly):
    try:
        with open(app_config['datastore']['filename'], 'r') as f:
            anomalies = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        anomalies = []
    
    anomalies.append(anomaly)
    
    with open(app_config['datastore']['filename'], 'w') as f:
        json.dump(anomalies, f, indent=2)
    
    logger.info(f"Stored anomaly with event_id {anomaly['event_id']}")
    
def process_messages():
    """ Process event messages """
    hostname = "%s:%d" % (app_config["events"]["hostname"],
                          app_config["events"]["port"])
        
    client = KafkaClient(hosts=hostname)
    topic = client.topics[str.encode(app_config["events"]["topic"])]
    
    logger.info(f"Connected to Kafka topic: {app_config['events']['topic']}")
    
    consumer = topic.get_simple_consumer(consumer_group=b'anomaly_group',
                                       reset_offset_on_start=False,
                                       auto_offset_reset=OffsetType.EARLIEST)
    
    for msg in consumer:
        msg_str = msg.value.decode('utf-8')
        msg = json.loads(msg_str)
        logger.info(f"Received event message: {msg}")
        
        payload = msg["payload"]
        
        if msg["type"] == "location_reading":
            altitude = payload.get("altitude")
            if altitude > app_config['thresholds']['altitude_high']:
                anomaly = {
                    'event_id': payload['client_id'],
                    'trace_id': payload['trace_id'],
                    'event_type': 'location - altitude',
                    'anomaly_type': 'Too High',
                    'description': f"altitude value {bp_value} exceeds threshold of {app_config['thresholds']['altitude_high']}",
                    'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                store_anomaly(anomaly)
            elif altitude < app_config['thresholds']['bp_low']:
                anomaly = {
                    'event_id': payload['client_id'],
                    'trace_id': payload['trace_id'],
                    'event_type': 'location - altitude',
                    'anomaly_type': 'Too Low',
                    'description': f"altitude value {bp_value} is below threshold of {app_config['thresholds']['altitude_low']}",
                    'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                store_anomaly(anomaly)
                
        elif msg["type"] == "time_until_arrival_reading":
            time_difference_in_ms = payload.get("time_difference_in_ms")
            if time_difference_in_ms > app_config['thresholds']['time_difference_in_ms_high']:
                anomaly = {
                    'event_id': payload['flight_id'],
                    'trace_id': payload['trace_id'],
                    'event_type': 'time_until_arrival - time_difference_in_ms',
                    'anomaly_type': 'Too High',
                    'description': f"time_difference_in_ms {hr_value} exceeds threshold of {app_config['thresholds']['time_difference_in_ms_high']}",
                    'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                store_anomaly(anomaly)
            elif time_difference_in_ms < app_config['thresholds']['time_difference_in_ms_low']:
                anomaly = {
                    'event_id': payload['flight_id'],
                    'trace_id': payload['trace_id'],
                    'event_type': 'time_until_arrival - time_difference_in_ms',
                    'anomaly_type': 'Too Low',
                    'description': f"time_difference_in_ms {hr_value} is below threshold of {app_config['thresholds']['time_difference_in_ms_low']}",
                    'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                store_anomaly(anomaly)
        
        consumer.commit_offsets()
        
def init_datastore():
    if not os.path.exists(app_config['datastore']['filename']):
        with open(app_config['datastore']['filename'], 'w') as f:
            json.dump([], f)

def get_anomalies(anomaly_type=None):
    logger.info(f"GET /anomalies request received - anomaly_type={anomaly_type}")
    
    try:
        with open(app_config['datastore']['filename'], 'r') as f:
            anomalies = json.load(f)
    except FileNotFoundError:
        return {"message": "Anomalies data store not found"}, 404
    
    valid_types = ['Too High', 'Too Low']
    if anomaly_type and anomaly_type not in valid_types:
        return {"message": f"Invalid anomaly type. Must be one of {valid_types}"}, 400
    
    if anomaly_type:
        anomalies = [a for a in anomalies if a['anomaly_type'] == anomaly_type]
    
    if not anomalies:
        return {"message": "No anomalies found"}, 404
        
    anomalies.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return anomalies, 200

app.add_api("openapi.yml", strict_validation=True, validate_responses=True)

if __name__ == "__main__":
    init_datastore()
    
    t1 = Thread(target=process_messages)
    t1.setDaemon(True)
    t1.start()
    
    app.run(host='0.0.0.0', port=8120)