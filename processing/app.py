import connexion
from connexion import NoContent
from datetime import datetime
import yaml
import logging, logging.config
from apscheduler.schedulers.background import BackgroundScheduler
import json
import requests
import swagger_ui_bundle
import os
from connexion import FlaskApp
from connexion.middleware import MiddlewarePosition
from starlette.middleware.cors import CORSMiddleware

def get_stats():
    logger.info("Get stats request has started")

    try:
        with open(app_config['datastore']['filename'], 'r') as f:
            stats = json.load(f)
    except FileNotFoundError:
        logger.error("Statistics file not found")
        return {'message': 'Statistics do not exist'}, 404

    response = {
        "num_location_readings": stats.get("num_location_readings", 0),
        "max_location_latitude_reading": stats.get("max_location_latitude_reading", 0.0),
        "num_time_until_arrival_readings": stats.get("num_time_until_arrival_readings", 0),
        "max_time_until_arrival_time_difference_in_ms_reading": stats.get("max_time_until_arrival_time_difference_in_ms_reading", 0),
        'last_updated': "2024-10-15T09:56:32.977743"
    }

    logger.debug(f"Returning stats: {response}")
    logger.info("Get stats request has completed")

    return response, 200

def populate_stats():
    """periodically update stats"""
    logger.info("Start populating stats")

    default_stats = {
        'num_location_readings': 0,
        'max_location_latitude_reading': 0,
        'num_time_until_arrival_readings': 0,
        'max_time_until_arrival_time_difference_in_ms_reading': 0,
        'last_updated': "2024-10-15T09:56:32.977743"
    }

    filename = app_config['datastore']['filename']
    
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            stats = json.load(f)
    else:
        with open(filename, 'w') as f:
            stats = default_stats
            json.dump(stats, f, indent=4)
    
    last_updated = stats.get('last_updated', '2024-01-15T09:56:32.977743')
    current_time = datetime.now().isoformat()
    logger.debug(f"Querying location events from {last_updated} to {current_time}")

    location_url=requests.get(app_config['eventstore']['url'] + "/readings/location?start_timestamp=" + last_updated + "&end_timestamp=" + current_time)
    time_until_arrival_url=requests.get(app_config['eventstore']['url'] + "/readings/time-until-arrival?start_timestamp=" + last_updated + "&end_timestamp=" + current_time)
    
    print(location_url.status_code)
    print(location_url.text)
    logger.debug(f"Querying location events from {last_updated} to {current_time}")
    
    try:
        if location_url.status_code == 201:
            location_events = location_url.json()
            print("LOCATION_URL.JSON\n\n",location_events)

            #number of location readings
            num_location_events = len(location_events)
            stats['num_location_readings'] += num_location_events 

            #max latitude
            if location_events:
                max_latitude = max(event['latitude'] for event in location_events)
            else:
                max_latitude = stats['max_location_latitude_reading']
            stats['max_location_latitude_reading'] = max(stats['max_location_latitude_reading'], max_latitude)

            logger.info(f"Received {num_location_events} aircraft location events")
        else:
            logger.error(f"Failed to get aircraft location events - status code: {location_url.status_code}")

        if time_until_arrival_url.status_code == 201:
            time_until_arrival_events = time_until_arrival_url.json()

            #number of time until arrival readings
            num_time_until_arrival_events = len(time_until_arrival_events)
            stats['num_time_until_arrival_readings'] += num_time_until_arrival_events

            #max time until arrival
            if time_until_arrival_events:
                max_time_diff = max(event['time_difference_in_ms'] for event in time_until_arrival_events)
            else:
                max_time_diff = stats['max_time_until_arrival_time_difference_in_ms_reading']
            stats['max_time_until_arrival_time_difference_in_ms_reading'] = max(stats['max_time_until_arrival_time_difference_in_ms_reading'], max_time_diff)

            logger.info(f"Received {num_time_until_arrival_events} time until arrival events")
        else:
            logger.error(f"Failed to get time until arrival events - status code: {time_until_arrival_url.status_code}")

        stats['last_updated'] = current_time
        logger.debug(f"Updated stats: {stats}")
        with open(filename, 'w') as f:
            json.dump(stats, f, indent=4)
        
        logger.info("Finished populating stats")

    except Exception as e:
        logger.error(f"Error occurred while updating stats: {str(e)}")
        

def init_scheduler():
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(populate_stats, 'interval', seconds=app_config['scheduler']['period_sec'])
    sched.start()

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


app = connexion.FlaskApp(__name__, specification_dir='')
app.add_api("lli249-Aircraft-Readings-1.0.0-resolved.yaml",
            base_path="/processing", 
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

if __name__ == "__main__":
    populate_stats()
    init_scheduler()
    app.run(host='0.0.0.0',port=8100)
