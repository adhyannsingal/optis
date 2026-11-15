"""Translate recent phone fixes into one checked route's local metre frame."""
import math
from datetime import UTC, datetime
from time import monotonic

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from .navigation import Fix, Navigation, Thresholds
from .routes import RouteError, validate_route


class PhoneFix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seq: int = Field(ge=0, strict=True)
    lat_deg: FiniteFloat = Field(ge=-90, le=90)
    lon_deg: FiniteFloat = Field(ge=-180, le=180)
    horizontal_accuracy_m: FiniteFloat = Field(gt=0)
    fix_time_utc: datetime
    age_at_send_ms: int = Field(ge=0, strict=True)


def fix_age(packet, now):
    wall_age = (now - packet.fix_time_utc).total_seconds()
    sent_age = packet.age_at_send_ms / 1000
    if not -1 <= wall_age - sent_age <= 2:
        return None
    return max(wall_age, sent_age, 0)


def usable_origin(packet, now):
    age = fix_age(packet, now)
    limits = Thresholds()
    return age is not None and age <= limits.max_age and packet.horizontal_accuracy_m <= limits.max_accuracy


class PhoneRoute:
    def __init__(self, document, *, mapped_paths=None):
        if mapped_paths is None and document.get("verified") is not True:
            raise RouteError("The local route must be physically checked before enabling live guidance.")
        self.route_id = document["id"]
        points = document["waypoints"]
        if len(points) < 2 or not all(
            len(point) == 2 and -85 <= point[0] <= 85 and -180 <= point[1] <= 180
            for point in points
        ):
            raise RouteError("Expected at least two valid latitude/longitude waypoints.")
        self.latitude, self.longitude = points[0]
        local = [list(self.project(*point)) for point in points]
        if mapped_paths is None and any(math.hypot(*point) > 1000 for point in local):
            raise RouteError("The first live route is limited to a local test area.")
        route = dict(name=document["name"], simulated=False, points=local, instructions=document["instructions"])
        if mapped_paths is not None:
            route["paths"] = [[list(self.project(*point)) for point in path] for path in mapped_paths]
        self.geometry = validate_route(route, allow_live=True)
        self.mapped_paths = mapped_paths
        self.reset()

    def reset(self):
        self.sequence = -1
        self.started_wall = datetime.now(UTC)
        self.last_good = None
        self.origin_confirmed = False
        self.accepted_position = None

    def project(self, latitude, longitude):
        delta_longitude = (longitude - self.longitude + 180) % 360 - 180
        metres_per_degree = math.pi * 6371000 / 180
        return (
            delta_longitude * metres_per_degree * math.cos(math.radians(self.latitude)),
            (latitude - self.latitude) * metres_per_degree,
        )

    def update(self, navigation: Navigation, packet: PhoneFix):
        now = monotonic()
        if not navigation.active or navigation.paused:
            return navigation.tick(now)
        if packet.fix_time_utc.utcoffset() is None:
            raise ValueError("Fix timestamp must include a UTC offset.")
        if packet.seq <= self.sequence:
            return navigation.tick(now)
        age = fix_age(packet, datetime.now(UTC))
        # The difference includes network transit and wall-clock skew. Hold if
        # the clocks disagree by more than the small allowed local-link budget.
        if packet.fix_time_utc < self.started_wall or age is None:
            self.last_good = None
            return navigation.weak_signal()
        self.sequence = packet.seq
        x, y = self.project(packet.lat_deg, packet.lon_deg)
        fix = Fix(now - age, x, y, packet.horizontal_accuracy_m)
        if age > navigation.thresholds.max_age or fix.accuracy > navigation.thresholds.max_accuracy:
            self.last_good = None
            return navigation.weak_signal()
        previous = self.last_good
        if previous:
            elapsed = fix.timestamp - previous.timestamp
            if elapsed <= 0:
                return navigation.tick(now)
            if elapsed <= navigation.thresholds.max_age and math.hypot(
                fix.x - previous.x, fix.y - previous.y
            ) > 3 * elapsed + previous.accuracy + fix.accuracy:
                return navigation.weak_signal("Location jumped unexpectedly. Route progress is paused.")
        if not self.origin_confirmed:
            if math.hypot(fix.x, fix.y) > navigation.thresholds.corridor:
                return navigation.weak_signal("Start near the beginning of the checked route.")
            self.origin_confirmed = True
        self.last_good = fix
        result = navigation.update(fix, now)
        if result["status"] in {"off_route", "detour", "missed_turn", "weak_signal", "invalid_fix", "ignored_fix"}:
            self.last_good = previous
        else:
            self.accepted_position = (packet.lat_deg, packet.lon_deg)
        return result
