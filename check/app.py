import requests
from requests.exceptions import Timeout, ConnectionError
import connexion
import json
import os
import yaml
import logging
import logging.config
import requests
import datetime
from requests.exceptions import Timeout, ConnectionError
from apscheduler.schedulers.background import BackgroundScheduler
from connexion import FlaskApp
from connexion.middleware import MiddlewarePosition
from starlette.middleware.cors import CORSMiddleware

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

def init_scheduler():
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(check_services, 
                  'interval', 
                  seconds=app_config['check']['scheduler']['period_sec'])
    sched.start()


RECEIVER_URL = app_config['check']['url']['receiver']
STORAGE_URL = app_config['check']['url']['storage']
PROCESSING_URL = app_config['check']['url']['processing']
ANALYZER_URL = app_config['check']['url']['analyzer']
TIMEOUT = app_config['check']['timeout_sec'] # Set to 2 seconds in your config file

def check_services():
    """ Called periodically """
    status = {}
    receiver_status = "Unavailable"
    try:
        response = requests.get(RECEIVER_URL, timeout=TIMEOUT)
        if response.status_code == 200:
            receiver_status = "Healthy"
            logger.info("Receiver is Healthy")
        else:
            logger.info("Receiver returning non-200 response")
    except (Timeout, ConnectionError):
        logger.info("Receiver is Not Available")
    status['receiver'] = receiver_status

    storage_status = "Unavailable"
    try:
        response = requests.get(STORAGE_URL, timeout=TIMEOUT)
        if response.status_code == 200:
            storage_json = response.json()
            storage_status = f"Storage has {storage_json['num_location_readings']} Location and {storage_json['num_time_until_arrival_readings']} Time_until_arrival events"
            logger.info("Storage is Healthy")
        else:
            logger.info("Storage returning non-200 response")
    except (Timeout, ConnectionError):
        logger.info("Storage is Not Available")
    status['storage'] = storage_status

    processing_status = "Unavailable"
    try:
        response = requests.get(PROCESSING_URL, timeout=TIMEOUT)
        if response.status_code == 200:
            processing_json = response.json()
            processing_status = f"Processing has {processing_json['num_location_readings']} Location and {processing_json['num_time_until_arrival_readings']} Time_until_arrival events"
            logger.info("Processing is Healthy")
        else:
            logger.info("Processing returning non-200 response")
    except (Timeout, ConnectionError):
        logger.info("Processing is Not Available")
    status['processing'] = processing_status

    analyzer_status = "Unavailable"
    try:
        response = requests.get(ANALYZER_URL, timeout=TIMEOUT)
        if response.status_code == 200:
            analyzer_json = response.json()
            analyzer_status = f"Analyzer has {analyzer_json['location_reading']} Location and {analyzer_json['time_until_arrival_reading']} Time_until_arrival events"
            logger.info("Analyzer is Healthy")
        else:
            logger.info("Analyzer returning non-200 response")
    except (Timeout, ConnectionError):
        logger.info("Analyzer is Not Available")
    status['analyzer'] = analyzer_status

    status_file = app_config['check']['status_file']
    os.makedirs(os.path.dirname(status_file), exist_ok=True)

    with open(status_file, 'w') as f:
        json.dump(status, f, indent=4)

def get_checks():
    if os.path.exists(app_config['check']['status_file']):
        with open(app_config['check']['status_file']) as f:
            status = json.load(f)
        return status, 200
    else:
        return {"message": "Status file not found"}, 404

app = connexion.FlaskApp(__name__, specification_dir='')
app.add_api("openapi.yml",base_path="/check", strict_validation=True, validate_responses=True)

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

if __name__ == "__main__":
    init_scheduler()
    app.run(port=8130)