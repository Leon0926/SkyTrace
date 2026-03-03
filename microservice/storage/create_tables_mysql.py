import mysql.connector
db_conn = mysql.connector.connect(host="localhost", user="user",password="ACIT3855", database="events")
db_cursor = db_conn.cursor()
db_cursor.execute('''
CREATE TABLE aircraft_location
(id INT NOT NULL AUTO_INCREMENT,
flight_id VARCHAR(250) NOT NULL,
latitude VARCHAR(250) NOT NULL,
longitude VARCHAR(250) NOT NULL,
timestamp VARCHAR(100) NOT NULL,
trace_id VARCHAR(100) NOT NULL,
date_created VARCHAR(100) NOT NULL,
CONSTRAINT aircraft_location_pk PRIMARY KEY (id))
''')
db_cursor.execute('''
CREATE TABLE aircraft_time_until_arrival
(id INT NOT NULL AUTO_INCREMENT,
flight_id VARCHAR(250) NOT NULL,
estimated_arrival_time VARCHAR(250) NOT NULL,
actual_arrival_time VARCHAR(250) NOT NULL,
time_difference_in_ms INTEGER NOT NULL,
timestamp VARCHAR(100) NOT NULL,
date_created VARCHAR(100) NOT NULL,
trace_id VARCHAR(100) NOT NULL,
CONSTRAINT aircraft_time_until_arrival_pk PRIMARY KEY (id))
''')
db_conn.commit()
db_conn.close()
