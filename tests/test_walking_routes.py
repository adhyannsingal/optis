from contextlib import closing
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
from threading import Event, Thread
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from optis.api import create_app
from optis.interaction.voice import command
from optis.navigation.valhalla import Destination, Valhalla


START = (42.0, -72.0)
CORNER = (42.00020, -72.0)
END = (42.00020, -71.9998)


def encode_shape(points):
    previous = [0, 0]
    encoded = []
    for point in points:
        for axis, value in enumerate(point):
            current = round(value * 1e6)
            delta = current - previous[axis]
            previous[axis] = current
            value = (delta << 1) ^ (-1 if delta < 0 else 0)
            while value >= 32:
                encoded.append(chr((value & 31 | 32) + 63))
                value >>= 5
            encoded.append(chr(value + 63))
    return "".join(encoded)


class WalkingRoutes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dest = Destination("Example public library", *END)
        self.router = MagicMock(spec=Valhalla)
        index = Path(self.temp.name) / "places.sqlite3"
        with closing(sqlite3.connect(index)) as connection, connection:
            connection.execute("CREATE VIRTUAL TABLE places USING fts5(name, lat UNINDEXED, lon UNINDEXED)")
            connection.execute("INSERT INTO places VALUES (?, ?, ?)", (self.dest.name, self.dest.lat, self.dest.lon))
        self.router.search.side_effect = Valhalla("http://localhost:8002", index).search
        self.router.plan.return_value = ([[START, (42.0001, -72.00016), CORNER], [CORNER, END]], [
            "Follow the sidewalk.", "Turn right onto the path.",
        ])
        app = create_app(database=Path(self.temp.name) / "memory.sqlite3", token="test", router=self.router)
        self.client = TestClient(app, headers={"Authorization": "Bearer test"})
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def intent(self, kind, **fields):
        return self.client.post("/v1/intent", json={"request_id": kind, "kind": kind, **fields})

    def fix(self, seq, point, *, age=0, accuracy=4):
        timestamp = datetime.now(UTC) - timedelta(seconds=age)
        response = self.client.post("/v1/location", json={
            "seq": seq, "lat_deg": point[0], "lon_deg": point[1], "horizontal_accuracy_m": accuracy,
            "fix_time_utc": timestamp.isoformat(), "age_at_send_ms": age * 1000,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_phone_token_is_limited_to_sending_fixes(self):
        with TestClient(create_app(database=Path(self.temp.name) / "scoped.sqlite3", token="web",
                                   location_token="phone", router=self.router)) as client:
            headers = {"Authorization": "Bearer phone"}
            now = datetime.now(UTC).isoformat()
            fix = dict(seq=1, lat_deg=42.0, lon_deg=-72.0, horizontal_accuracy_m=5,
                       fix_time_utc=now, age_at_send_ms=0)
            self.assertEqual(client.get("/v1/status", headers=headers).status_code, 401)
            self.assertEqual(client.post("/v1/location", json=fix, headers=headers).status_code, 200)
            self.assertTrue(client.get("/v1/status", headers={"Authorization": "Bearer web"}).json()["location"]["usable"])

    def test_new_destination_requires_fresh_gps_and_waits_on_dropout(self):
        results = self.intent("find_destination", query="public library").json()
        self.assertEqual(results["status"], "destinations")
        selection = results["data"][0]
        self.assertEqual(self.intent("walk_to", destination=selection).status_code, 409)
        self.fix(1, START, age=15)
        self.assertEqual(self.intent("walk_to", destination=selection).status_code, 409)
        self.fix(2, START, accuracy=30)
        self.assertEqual(self.intent("walk_to", destination=selection).status_code, 409)
        self.assertEqual(self.fix(3, START)["status"], "fix_received")
        route = self.intent("walk_to", destination=selection)
        self.assertEqual(route.json()["status"], "route_started", route.text)
        self.router.plan.assert_called_once_with(START, self.dest)
        self.assertEqual(self.fix(4, START)["status"], "guidance")
        self.assertFalse(route.json()["data"]["simulated"])
        from time import monotonic
        with patch("optis.api.monotonic", return_value=monotonic() + 6):
            self.assertEqual(self.client.get("/v1/status").json()["route"]["status"], "weak_signal")

    def test_stop_cancels_a_pending_plan(self):
        entered, release, responses = Event(), Event(), []
        paths = self.router.plan.return_value

        def waiting_plan(*args):
            entered.set()
            if not release.wait(2):
                raise TimeoutError("Test did not release planner")
            return paths

        self.router.plan.side_effect = waiting_plan
        self.fix(1, START)
        destination = {"name": self.dest.name, "lat": self.dest.lat, "lon": self.dest.lon}
        thread = Thread(target=lambda: responses.append(self.intent("walk_to", destination=destination)))
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.intent("stop").json()["status"], "stopped")
        finally:
            release.set()
            thread.join(2)
        self.assertEqual(responses[0].status_code, 409)
        self.assertIsNone(self.client.get("/v1/status").json()["route"])

    def test_valhalla_request_and_maneuver_paths(self):
        from optis.navigation.navigation import Fix, Navigation

        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "trip": {"legs": [{
                "shape": encode_shape([START, START, (42.0001, -72.00016), CORNER, END]),
                "maneuvers": [
                    {"begin_shape_index": 0, "end_shape_index": 3, "instruction": "Follow the sidewalk."},
                    {"begin_shape_index": 3, "end_shape_index": 4, "instruction": "Turn right."},
                    {"begin_shape_index": 4, "end_shape_index": 4, "instruction": "Arrive."},
                ],
            }]},
        }).encode()
        with patch("optis.navigation.valhalla.urlopen", return_value=response) as fetch:
            paths, instructions = Valhalla("http://localhost:8002").plan(START, self.dest)
        self.assertEqual(json.loads(fetch.call_args.args[0].data)["costing"], "pedestrian")
        self.assertEqual(paths[0][1], (42.0001, -72.00016))
        self.assertEqual(instructions, ["Follow the sidewalk.", "Turn right."])
        route = Navigation({"name": "Library", "simulated": False,
                            "points": [[0, 0], [0, 20], [20, 20]],
                            "paths": [[[0, 0], [-16, 10], [0, 20]], [[0, 20], [20, 20]]],
                            "instructions": instructions}, live=True)
        route.start()
        self.assertEqual(route.update(Fix(1, -16, 10, 4), 1)["status"], "guidance")
        self.assertEqual(route.update(Fix(2, 0, 20, 4), 2)["data"]["step"], 0)
        self.assertEqual(route.update(Fix(3, 0, 20, 4), 3)["status"], "turn")
        self.assertEqual(route.update(Fix(4, 20, 20, 4), 4)["status"], "near_destination")
        self.assertEqual(route.update(Fix(5, 20, 20, 4), 5)["status"], "arrived")
        self.assertEqual(command("Take me to the library.")["kind"], "find_destination")
