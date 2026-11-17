import uuid
import time
from typing import Dict, Any, Optional

VALID_SENSOR_TYPES = {"environmental", "traffic", "weather"}
VALID_DISTRICTS = {"central", "industrial", "residential", "waterfront", "suburban"}

class SensorReading:
    def __init__(
        self,
        station_id: str,
        district_id: str,
        sensor_type: str,
        data: Dict[str, Any],
        reading_id: Optional[str] = None,
        timestamp: Optional[float] = None,
        geo_location: Optional[Dict[str, float]] = None
    ):
        self.id = reading_id or str(uuid.uuid4())
        self.station_id = station_id
        self.district_id = district_id.lower()
        self.sensor_type = sensor_type.lower()
        self.data = data
        self.timestamp = timestamp or time.time()
        self.ingestion_timestamp = time.time()
        self.geo_location = geo_location or {"lat": 49.5883, "lon": 34.5514}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "station_id": self.station_id,
            "district_id": self.district_id,
            "sensor_type": self.sensor_type,
            "data": self.data,
            "timestamp": self.timestamp,
            "ingestion_timestamp": self.ingestion_timestamp,
            "geo_location": self.geo_location
        }

    @staticmethod
    def validate(payload: Dict[str, Any]) -> tuple[bool, str]:
        if not isinstance(payload, dict):
            return False, "Payload must be a JSON object"
        
        station_id = payload.get("station_id")
        if not station_id or not isinstance(station_id, str):
            return False, "Field 'station_id' is required and must be a string"
            
        district_id = payload.get("district_id")
        if not district_id or district_id.lower() not in VALID_DISTRICTS:
            return False, f"Field 'district_id' is invalid. Valid districts: {list(VALID_DISTRICTS)}"
            
        sensor_type = payload.get("sensor_type")
        if not sensor_type or sensor_type.lower() not in VALID_SENSOR_TYPES:
            return False, f"Field 'sensor_type' is invalid. Valid types: {list(VALID_SENSOR_TYPES)}"
            
        data = payload.get("data")
        if not isinstance(data, dict) or len(data) == 0:
            return False, "Field 'data' must be a non-empty object with telemetry metrics"
            
        return True, ""


class AlertEvent:
    def __init__(
        self,
        alert_type: str,
        severity: str,
        district_id: str,
        station_id: str,
        message: str,
        metric_name: str,
        metric_value: float,
        threshold_value: float,
        alert_id: Optional[str] = None,
        timestamp: Optional[float] = None
    ):
        self.id = alert_id or str(uuid.uuid4())
        self.alert_type = alert_type
        self.severity = severity
        self.district_id = district_id.lower()
        self.station_id = station_id
        self.message = message
        self.metric_name = metric_name
        self.metric_value = metric_value
        self.threshold_value = threshold_value
        self.timestamp = timestamp or time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "district_id": self.district_id,
            "station_id": self.station_id,
            "message": self.message,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "threshold_value": self.threshold_value,
            "timestamp": self.timestamp
        }
