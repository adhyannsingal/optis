"""Pedestrian route planning and offline lookup in an OpenStreetMap place index."""

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .routes import RouteError, number


@dataclass(frozen=True)
class Destination:
    name: str
    lat: float
    lon: float


class RoutingUnavailable(RouteError):
    pass


def valid_coordinates(lat, lon):
    return number(lat) and number(lon) and -85 <= lat <= 85 and -180 <= lon <= 180


def destination_coordinates(query):
    if "," not in query:
        return None
    try:
        lat, lon = map(float, query.split(",", maxsplit=1))
    except ValueError:
        return None
    if not valid_coordinates(lat, lon):
        raise RouteError("Enter valid latitude and longitude.")
    return Destination("Selected coordinates", lat, lon)


def decode_shape(shape):
    if not isinstance(shape, str) or not shape or len(shape) > 500_000:
        raise RouteError("Valhalla returned an invalid route shape.")
    values = [0, 0]
    coordinate = component = shift = 0
    points = []
    for char in shape:
        chunk = ord(char) - 63
        if not 0 <= chunk <= 63 or shift > 30:
            raise RouteError("Valhalla returned an invalid route shape.")
        component |= (chunk & 31) << shift
        if chunk & 32:
            shift += 5
            continue
        values[coordinate] += ~(component >> 1) if component & 1 else component >> 1
        component = shift = 0
        coordinate ^= 1
        if coordinate == 0:
            point = values[0] / 1e6, values[1] / 1e6
            if not valid_coordinates(*point):
                raise RouteError("Valhalla returned invalid route coordinates.")
            points.append(point)
    if shift or coordinate or len(points) < 2:
        raise RouteError("Valhalla returned an incomplete route shape.")
    return points


class Valhalla:
    def __init__(self, url, places_path=None):
        self.url = url.rstrip("/") + "/route"
        self.places = Path(places_path).resolve().as_uri() + "?mode=ro" if places_path else None

    def search(self, query, origin=None):
        if coordinates := destination_coordinates(query):
            return [coordinates]
        words = re.findall(r"[^\W_]+", query.casefold())
        if not words or not self.places:
            return []
        match = " AND ".join(f'"{word}"' for word in words)
        order, params = "rank, name", [match]
        if origin:
            lat, lon = origin
            scale = math.cos(math.radians(lat)) ** 2
            order = "(lat-?)*(lat-?) + (lon-?)*(lon-?)*?, rank, name"
            params.extend([lat, lat, lon, lon, scale])
        try:
            database = sqlite3.connect(self.places, uri=True)
            try:
                rows = database.execute(
                    "SELECT name, lat, lon FROM places WHERE places MATCH ? ORDER BY " + order + " LIMIT 6",
                    params,
                ).fetchall()
            finally:
                database.close()
        except sqlite3.Error:
            raise RoutingUnavailable("The local place-name index is unavailable. Use coordinates or build the index.") from None
        return [Destination(*row) for row in rows]

    def plan(self, origin, destination):
        body = json.dumps({
            "locations": [
                {"lat": origin[0], "lon": origin[1]},
                {"lat": destination.lat, "lon": destination.lon},
            ],
            "costing": "pedestrian",
            "units": "kilometers",
        }).encode()
        request = Request(self.url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=8) as response:
                data = json.loads(response.read(2_000_000))
        except HTTPError as error:
            if error.code in {400, 404, 422}:
                raise RouteError("No walking route is available for those locations in the loaded map.") from None
            raise RoutingUnavailable("Valhalla is unavailable. Try again once the service is ready.") from None
        except (URLError, TimeoutError, ValueError):
            raise RoutingUnavailable("Valhalla is unavailable. Try again once the service is ready.") from None
        try:
            leg, = data["trip"]["legs"]
            points = decode_shape(leg["shape"])
            paths, instructions = [], []
            end = 0
            for maneuver in leg["maneuvers"]:
                start, finish = maneuver["begin_shape_index"], maneuver["end_shape_index"]
                if type(start) is not int or type(finish) is not int or not 0 <= start <= finish < len(points) or start != end:
                    raise ValueError("Invalid maneuver indices")
                end = finish
                # Valhalla can repeat a junction at the precision of its shape.
                path = [points[start], *(points[i] for i in range(start + 1, finish + 1)
                                         if points[i] != points[i - 1])]
                if len(path) < 2:
                    continue
                text = maneuver["instruction"]
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Missing maneuver cue")
                paths.append(path)
                instructions.append(text)
            if end != len(points) - 1 or not paths:
                raise ValueError("Incomplete maneuvers")
        except (KeyError, TypeError, ValueError):
            raise RoutingUnavailable("Valhalla returned unreadable walking directions.") from None
        return paths, instructions
