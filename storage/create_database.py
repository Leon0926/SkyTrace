from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

Base = declarative_base()

class AircraftLocation(Base):
    __tablename__ = 'aircraft_location'
    id = Column(Integer, primary_key=True)
    flight_id = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    date_created = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    trace_id = Column(String, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "flight_id": self.flight_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timestamp": self.timestamp,
            "date_created": self.date_created,
            "trace_id": self.trace_id
        }



class ArrivalTime(Base):
    __tablename__ = 'aircraft_time_until_arrival'
    id = Column(Integer, primary_key=True)
    flight_id = Column(String, nullable=False)
    estimated_arrival_time = Column(String, nullable=False)
    actual_arrival_time = Column(String, nullable=False)
    time_difference_in_ms = Column(Integer, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    date_created = Column(DateTime, nullable=False)
    trace_id = Column(String, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "flight_id": self.flight_id,
            "estimated_arrival_time": self.estimated_arrival_time,
            "actual_arrival_time": self.actual_arrival_time,
            "time_difference_in_ms": self.time_difference_in_ms,
            "timestamp": self.timestamp,
            "date_created": self.date_created,
            "trace_id": self.trace_id
        }

# Create the SQLite database
def create_database():
    engine = create_engine('sqlite:///events.db')
    Base.metadata.create_all(engine)
    print("Database created with two tables: aircraft_location and arrival_time")

if __name__ == "__main__":
    create_database()
