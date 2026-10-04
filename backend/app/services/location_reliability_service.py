"""
Location Reliability & GPS Anomaly Detection Service (Phase 13).

Provides:
- Mechanic heartbeat freshness calculation (fresh, stale, offline)
- GPS coordinate quality validation
- Anomaly detection: impossible speed, large jumps, poor accuracy, spoofing
- Audit record persistence in public.mechanic_location_anomalies
"""

from datetime import datetime, timezone
import math
from typing import Any
import uuid

from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client

logger = get_logger("services.location_reliability")


class LocationReliabilityService:
    """Evaluates location freshness and detects GPS anomalies."""

    # Operational thresholds
    FRESH_THRESHOLD_SECONDS: float = 60.0
    STALE_THRESHOLD_SECONDS: float = 300.0
    MAX_SPEED_KMH: float = 160.0
    MAX_JUMP_METERS_PER_MINUTE: float = 2000.0
    MAX_ACCEPTABLE_ACCURACY_METERS: float = 500.0

    def __init__(self, client: Any = None):
        self.client = client or get_supabase_service_client()

    @classmethod
    def evaluate_freshness(cls, updated_at_str: str | datetime | None) -> str:
        """
        Classify mechanic location freshness based on last ping timestamp.
        Returns: 'fresh', 'stale', or 'offline'.
        """
        if not updated_at_str:
            return "offline"

        now = datetime.now(timezone.utc)
        if isinstance(updated_at_str, str):
            try:
                dt = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            except Exception:
                return "offline"
        else:
            dt = updated_at_str

        delta_seconds = (now - dt).total_seconds()
        if delta_seconds <= cls.FRESH_THRESHOLD_SECONDS:
            return "fresh"
        elif delta_seconds <= cls.STALE_THRESHOLD_SECONDS:
            return "stale"
        else:
            return "offline"

    @staticmethod
    def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate great-circle distance between two points in meters."""
        r = 6371000.0  # Earth radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return r * c

    async def validate_and_record_ping(
        self,
        mechanic_id: uuid.UUID,
        latitude: float,
        longitude: float,
        accuracy_meters: float | None = None,
        booking_id: uuid.UUID | None = None,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """
        Validate GPS coordinates and detect anomalies against previous location ping.
        Returns: (is_valid, list_of_anomalies).
        """
        anomalies: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        # 1. Coordinate boundary check
        if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
            anomalies.append({
                "anomaly_type": "invalid_coordinates",
                "severity": "high",
                "notes": f"Coordinates out of bounds: lat={latitude}, lng={longitude}",
            })

        # 2. Accuracy check
        if accuracy_meters is not None and accuracy_meters > self.MAX_ACCEPTABLE_ACCURACY_METERS:
            anomalies.append({
                "anomaly_type": "poor_accuracy",
                "severity": "low",
                "notes": f"GPS accuracy ({accuracy_meters}m) exceeds acceptable limit ({self.MAX_ACCEPTABLE_ACCURACY_METERS}m)",
            })

        # 3. Retrieve prior location
        prev_res = (
            self.client.table("mechanic_profiles")
            .select("current_latitude, current_longitude, current_location_updated_at")
            .eq("id", str(mechanic_id))
            .execute()
        )

        prev_loc = None
        dist_m = None
        time_delta_s = None
        speed_kmh = None

        if prev_res.data and len(prev_res.data) > 0:
            profile = prev_res.data[0]
            p_lat = profile.get("current_latitude")
            p_lng = profile.get("current_longitude")
            p_time_str = profile.get("current_location_updated_at")

            if p_lat is not None and p_lng is not None and p_time_str:
                try:
                    p_dt = datetime.fromisoformat(p_time_str.replace("Z", "+00:00"))
                    prev_lat = float(p_lat)
                    prev_lng = float(p_lng)
                    time_delta_s = max(1.0, (now - p_dt).total_seconds())
                    dist_m = self.haversine_distance_meters(prev_lat, prev_lng, latitude, longitude)
                    speed_kmh = (dist_m / 1000.0) / (time_delta_s / 3600.0)

                    prev_loc = {"latitude": prev_lat, "longitude": prev_lng, "timestamp": p_time_str}

                    # Jump detection: high distance in short time
                    if time_delta_s <= 60.0 and dist_m > self.MAX_JUMP_METERS_PER_MINUTE:
                        anomalies.append({
                            "anomaly_type": "large_location_jump",
                            "severity": "high" if dist_m > 10000 else "medium",
                            "notes": f"Location jump of {round(dist_m)}m in {round(time_delta_s)}s",
                        })

                    # Impossible speed detection
                    if speed_kmh > self.MAX_SPEED_KMH and dist_m > 500:
                        anomalies.append({
                            "anomaly_type": "impossible_speed",
                            "severity": "high",
                            "notes": f"Calculated speed {round(speed_kmh, 1)} km/h exceeds limit ({self.MAX_SPEED_KMH} km/h)",
                        })

                except Exception as parse_exc:
                    logger.warning("failed_to_parse_prev_location", error=str(parse_exc))

        # 4. Persist any detected anomalies
        new_loc_json = {
            "latitude": latitude,
            "longitude": longitude,
            "accuracy_meters": accuracy_meters,
            "timestamp": now_iso,
        }

        for anomaly in anomalies:
            try:
                self.client.table("mechanic_location_anomalies").insert({
                    "mechanic_id": str(mechanic_id),
                    "booking_id": str(booking_id) if booking_id else None,
                    "detected_at": now_iso,
                    "previous_location": prev_loc,
                    "new_location": new_loc_json,
                    "distance_meters": dist_m,
                    "time_delta_seconds": time_delta_s,
                    "calculated_speed_kmh": round(speed_kmh, 2) if speed_kmh is not None else None,
                    "anomaly_type": anomaly["anomaly_type"],
                    "severity": anomaly["severity"],
                    "status": "flagged",
                    "notes": anomaly.get("notes"),
                }).execute()
            except Exception as ins_exc:
                logger.warning("failed_to_insert_location_anomaly", error=str(ins_exc))

        return len(anomalies) == 0, anomalies
