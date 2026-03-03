import mysql.connector
db_conn = mysql.connector.connect(host="localhost", port=3307, user="dbuser1",
password="ACIT3855", database="events")
db_cursor = db_conn.cursor()
db_cursor.execute('''
DROP TABLE aircraft_location, aircraft_time_until_arrival''')
db_conn.commit()
db_conn.close()