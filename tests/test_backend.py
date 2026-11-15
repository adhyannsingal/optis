from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
from time import monotonic
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from pharos.api import create_app
from pharos.navigation.location import PhoneRoute


class BackendChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "placements.sqlite3"
        self.headers = {"Authorization": "Bearer local-test"}
        self.route = PhoneRoute(dict(
            id="test", name="Checked test route", verified=True,
            waypoints=[[42, -72], [42.00006, -72], [42.00006, -71.9996]],
            instructions=["Follow the path.", "Turn right."],
        ))

    def client(self):
        return TestClient(create_app(database=self.database, token="local-test", checked_route=self.route))

    def intent(self, client, kind, **fields):
        result = client.post("/v1/intent", headers=self.headers,
                             json=dict(request_id="check", kind=kind, **fields))
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def fix(self, client, seq, latitude, longitude, age=0):
        packet = dict(seq=seq, lat_deg=latitude, lon_deg=longitude, horizontal_accuracy_m=4,
                      fix_time_utc=(datetime.now(UTC) - timedelta(seconds=age)).isoformat(),
                      age_at_send_ms=age * 1000)
        result = client.post("/v1/location", headers=self.headers, json=packet)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_memory_persists_and_arm_is_disabled(self):
        with self.client() as client:
            self.assertEqual(client.get("/v1/health").json()["arm"], "disabled")
            self.assertEqual(client.post("/v1/intent", json=dict(request_id="a", kind="scene")).status_code, 401)
            self.assertEqual(self.intent(client, "remember", item="keys", place="desk")["status"], "saved_placement")
        with self.client() as client:
            self.assertEqual(self.intent(client, "find", item="keys")["data"]["location"], "desk")
            self.assertEqual(self.intent(client, "retrieve", item="bottle")["status"], "arm_disabled")

    def test_keys_use_live_then_last_seen_then_saved_placement(self):
        class DemoCamera:
            camera_name = "test camera"
            matches = []

            def start(self, record):
                self.record = record

            def close(self):
                pass

            def snapshot(self):
                return "ready", {"detections": []}

            def keyring_snapshot(self):
                return self.matches

        camera = DemoCamera()
        app = create_app(database=self.database, token="local-test", camera=camera)
        with TestClient(app) as client:
            self.intent(client, "remember", item="keys", place="desk")
            camera.matches = [{"label": "keyring", "position": "left", "stable": True}]
            camera.record("keys", monotonic() * 1000)
            self.assertEqual(self.intent(client, "find", item="keys")["status"], "live_observation")
            camera.matches *= 2
            self.assertEqual(self.intent(client, "find", item="keys")["status"], "ambiguous")
            camera.matches = []
            result = self.intent(client, "find", item="keys")
            self.assertEqual(result["status"], "last_seen")
            self.assertNotIn("left", result["text"])
        with TestClient(create_app(database=self.database, token="local-test")) as client:
            self.assertEqual(self.intent(client, "find", item="keys")["data"]["camera"], "test camera")
            self.intent(client, "forget", item="keys")
            self.assertEqual(self.intent(client, "find", item="keys")["status"], "unavailable")

    def test_voice_key_file_is_private_and_can_be_added_after_start(self):
        key = self.database.parent / ".xai-key"
        app = create_app(database=self.database, token="local-test", voice_key_file=key)
        with TestClient(app) as client:
            self.assertFalse(client.get("/v1/health").json()["voice_configured"])
            key.write_text("dummy")
            key.chmod(0o644)
            self.assertFalse(client.get("/v1/health").json()["voice_configured"])
            key.chmod(0o600)
            self.assertTrue(client.get("/v1/health").json()["voice_configured"])

    def test_voice_uses_same_local_intent_and_restricts_commands(self):
        class DemoVoice:
            transcript = "Where are my keys?"

            def transcribe(self, audio, media_type):
                return self.transcript

            def speak(self, text):
                return b"demo", "audio/mpeg"

        voice = DemoVoice()
        app = create_app(database=self.database, token="local-test", voice=voice)
        with TestClient(app) as client:
            self.intent(client, "remember", item="keys", place="entryway table")
            headers = {**self.headers, "Content-Type": "audio/webm"}
            result = client.post("/v1/voice", headers=headers, content=b"sample").json()
            self.assertEqual(result["status"], "saved_placement")
            self.assertIn("entryway table", result["text"])
            self.assertEqual(result["audio_type"], "audio/mpeg")
            voice.transcript = "Activate the arm."
            result = client.post("/v1/voice", headers=headers, content=b"sample").json()
            self.assertEqual(result["status"], "unknown_command")

    def test_replay_completes_and_labels_simulation(self):
        with self.client() as client:
            result = self.intent(client, "start_route", route_id="standard")
            self.assertTrue(result["data"]["simulated"])
            updates = [self.intent(client, "next")["status"] for _ in range(10)]
            self.assertEqual(updates.count("turn"), 2)
            self.assertEqual(updates[-1], "arrived")

    def test_live_route_needs_recent_distinct_fixes(self):
        with self.client() as client:
            self.intent(client, "start_route", route_id="test")
            self.assertEqual(self.fix(client, 1, 42.00006, -72, age=20)["status"], "weak_signal")
            self.assertEqual(self.fix(client, 2, 42.0003, -72)["status"], "weak_signal")
            self.assertEqual(self.fix(client, 3, 42, -72)["status"], "guidance")
            first = self.fix(client, 4, 42.00006, -72)
            self.assertEqual(first["data"]["step"], 0)
            self.assertEqual(self.fix(client, 4, 42.00006, -72)["data"]["step"], 0)
            turn = self.fix(client, 5, 42.00006, -72)
            self.assertEqual(turn["status"], "turn")
            self.assertFalse(turn["data"]["simulated"])
            with patch("pharos.api.monotonic", return_value=monotonic() + 6):
                status = client.get("/v1/status", headers=self.headers).json()
                self.assertEqual(status["route"]["status"], "weak_signal")
                self.assertGreaterEqual(status["location"]["age_seconds"], 6)
                self.assertNotIn("lat_deg", status["location"])

            self.intent(client, "stop")
            self.assertIsNone(client.get("/v1/status", headers=self.headers).json()["route"])


if __name__ == "__main__":
    unittest.main()
