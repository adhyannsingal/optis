from datetime import UTC, datetime, timedelta
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
from threading import Event, Thread
from time import sleep
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from optis.api import create_app
from optis.interaction.voice import SpeechQueue, VoiceError, command
from optis.navigation.navigation import Fix, Navigation
from optis.navigation.routes import RouteError
from optis.navigation.valhalla import Destination, RoutingUnavailable, Valhalla


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

    def test_newer_plan_supersedes_slow_plan(self):
        entered, release, responses = Event(), Event(), []
        paths = self.router.plan.return_value
        calls = 0

        def planning(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                entered.set()
                release.wait(2)
            return paths

        self.router.plan.side_effect = planning
        self.fix(1, START)
        selected = {"name": self.dest.name, "lat": self.dest.lat, "lon": self.dest.lon}
        thread = Thread(target=lambda: responses.append(self.intent("walk_to", destination=selected)))
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.intent("walk_to", destination=selected).json()["status"], "route_started")
        finally:
            release.set()
            thread.join(2)
        self.assertEqual(responses[0].status_code, 409)
        self.assertTrue(self.client.get("/v1/status").json()["route_map"]["active"])

    def test_valhalla_request_and_maneuver_paths(self):
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
        self.assertEqual(command("Take me to the library.")["kind"], "navigate_to")

    def test_voice_starts_unique_place_and_requires_choice_for_ambiguity(self):
        self.assertEqual(command("Take me to W. E. B. Du Bois Library from Thatcher Hall.")["query"],
                         "W. E. B. Du Bois Library")
        self.assertEqual(command("Walk to Du Bois Library")["kind"], "navigate_to")
        self.assertEqual(command("Choose second")["choice"], 2)
        self.assertIsNone(command("Approve the arm"))
        self.assertEqual(self.intent("navigate_to", query="public library").status_code, 409)
        self.fix(1, START)
        self.assertEqual(self.intent("navigate_to", query="public library").json()["status"], "route_started")
        self.intent("stop")
        other = Destination("Other public library", 42.0004, -72.0004)
        self.router.search.side_effect = lambda query, origin: [self.dest, other]
        result = self.intent("navigate_to", query="public library").json()
        self.assertEqual(result["status"], "destinations")
        self.assertIn("1: Example public library", result["text"])
        self.assertIn("2: Other public library", result["text"])
        self.assertEqual(self.router.plan.call_count, 1)
        self.assertEqual(self.intent("choose_destination", choice=2).status_code, 200)
        self.assertEqual(self.router.plan.call_args.args[1], other)
        self.assertEqual(self.intent("choose_destination", choice=1).status_code, 409)

    def test_map_state_and_deliberate_recalculation(self):
        self.fix(1, START)
        selected = {"name": self.dest.name, "lat": self.dest.lat, "lon": self.dest.lon}
        self.assertEqual(self.intent("walk_to", destination=selected).json()["status"], "route_started")
        self.assertEqual(self.client.get("/v1/status").json()["route"]["status"], "route_started")
        state = self.client.get("/v1/status").json()["route_map"]
        self.assertTrue(state["active"])
        self.assertEqual(state["destination"], list(END))
        self.assertEqual(len(state["paths"]), 2)
        self.assertEqual(state["maneuvers"][1]["instruction"], "Turn right onto the path.")
        self.assertIsNone(state["position"])
        self.assertEqual(self.intent("recalculate").status_code, 409)
        self.fix(2, START)
        self.assertEqual(self.client.get("/v1/status").json()["route_map"]["position"], list(START))
        self.assertEqual(self.intent("recalculate").json()["status"], "route_started")
        self.intent("stop")
        self.assertFalse(self.client.get("/v1/status").json()["route_map"]["active"])

    def test_advance_turn_is_once_and_precedes_supported_turn(self):
        route = Navigation({"name": "Mapped route", "simulated": False,
                            "points": [[0, 0], [0, 40], [30, 40]],
                            "paths": [[[0, 0], [0, 40]], [[0, 40], [30, 40]]],
                            "instructions": ["Continue north.", "Turn right."]}, live=True)
        route.start()
        self.assertEqual(route.update(Fix(1, 0, 0, 3), 1)["status"], "guidance")
        self.assertEqual(route.update(Fix(2, 0, 25, 3), 2)["status"], "advance_turn")
        self.assertEqual(route.update(Fix(3, 0, 30, 3), 3)["status"], "progress")
        self.assertEqual(route.update(Fix(4, 0, 40, 3), 4)["data"]["step"], 0)
        self.assertEqual(route.update(Fix(5, 0, 40, 3), 5)["status"], "turn")

    def test_off_route_pause_recovery_and_arrival_hold(self):
        route = Navigation({"name": "Mapped route", "simulated": False,
                            "points": [[0, 0], [0, 40], [30, 40]],
                            "paths": [[[0, 0], [0, 40]], [[0, 40], [30, 40]]],
                            "instructions": ["Continue north.", "Turn right."]}, live=True)
        route.start()
        route.update(Fix(1, 0, 0, 3), 1)
        self.assertEqual(route.update(Fix(2, 20, 10, 3), 2)["status"], "off_route")
        self.assertEqual(route.last_state["status"], "off_route")
        self.assertEqual(route.update(Fix(6, 20, 10, 3), 6)["status"], "detour")
        self.assertEqual(route.pause()["status"], "route_paused")
        self.assertEqual(route.update(Fix(7, 0, 40, 3), 7)["status"], "route_paused")
        self.assertEqual(route.resume()["status"], "route_resumed")
        self.assertEqual(route.update(Fix(8, 0, 40, 15), 8)["status"], "weak_signal")
        self.assertEqual(route.update(Fix(9, 0, 40, 3), 9)["data"]["step"], 0)
        self.assertEqual(route.update(Fix(10, 0, 40, 3), 10)["status"], "turn")
        self.assertEqual(route.update(Fix(11, 30, 40, 3), 11)["status"], "near_destination")
        self.assertEqual(route.update(Fix(12, 30, 40, 3), 12)["status"], "arrived")

    def test_valhalla_rejects_malformed_and_no_route_responses(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"trip":{"legs":[{"shape":"?"}]}}'
        with patch("optis.navigation.valhalla.urlopen", return_value=response):
            with self.assertRaises((RouteError, RoutingUnavailable)):
                Valhalla("http://localhost:8002").plan(START, self.dest)
        from urllib.error import HTTPError
        with patch("optis.navigation.valhalla.urlopen", side_effect=HTTPError("x", 400, "", {}, None)):
            with self.assertRaisesRegex(RouteError, "No walking route"):
                Valhalla("http://localhost:8002").plan(START, self.dest)

    def test_speech_queue_deduplicates_and_discards_obsolete_audio(self):
        entered, release = Event(), Event()

        class Voice:
            def speak(self, text):
                entered.set()
                release.wait(2)
                if text == "failure":
                    raise VoiceError("xAI voice returned HTTP 503.")
                return text.encode(), "audio/mpeg"

        queue = SpeechQueue(lambda: Voice())
        cue = {"status": "guidance", "speech": "old", "data": {"step": 0}}
        queue.submit(cue)
        queue.submit(cue)
        self.assertTrue(entered.wait(2))
        queue.clear()
        release.set()
        sleep(.05)
        self.assertIsNone(queue.take())
        queue.submit({"status": "weak_signal", "speech": "failure", "data": {"step": 0}})
        for _ in range(100):
            if queue.status()["audio_error"]:
                break
            sleep(.01)
        self.assertIn("503", queue.status()["audio_error"])

    def test_spoken_route_starts_and_stop_cancels_pending_transcription(self):
        entered, release = Event(), Event()

        class Voice:
            wait = False

            def transcribe(self, audio, media_type):
                if self.wait:
                    entered.set()
                    release.wait(2)
                return "Take me to Du Bois Library from Thatcher Hall"

            def speak(self, text):
                return b"mock-audio", "audio/mpeg"

        voice = Voice()
        self.router.search.side_effect = lambda query, origin: [self.dest]
        app = create_app(database=Path(self.temp.name) / "voice.sqlite3", token="test",
                         router=self.router, voice=voice)
        with TestClient(app, headers={"Authorization": "Bearer test"}) as client:
            now = datetime.now(UTC).isoformat()
            self.assertEqual(client.post("/v1/location", json={
                "seq": 1, "lat_deg": START[0], "lon_deg": START[1],
                "horizontal_accuracy_m": 4, "fix_time_utc": now, "age_at_send_ms": 0,
            }).status_code, 200)
            result = client.post("/v1/voice", content=b"sample", headers={"Content-Type": "audio/webm"}).json()
            self.assertEqual(result["status"], "route_started")
            self.assertNotIn("audio", result)
            client.post("/v1/intent", json={"request_id": "stop", "kind": "stop"})
            voice.wait = True
            answers = []
            thread = Thread(target=lambda: answers.append(client.post(
                "/v1/voice", content=b"sample", headers={"Content-Type": "audio/webm"})))
            thread.start()
            try:
                self.assertTrue(entered.wait(2))
                client.post("/v1/intent", json={"request_id": "stop2", "kind": "stop"})
            finally:
                release.set()
                thread.join(2)
            self.assertEqual(answers[0].json()["status"], "stopped")
            self.assertIsNone(client.get("/v1/status").json()["route"])
