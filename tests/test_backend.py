from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
import unittest

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
            self.intent(client, "stop")
            self.assertIsNone(client.get("/v1/status", headers=self.headers).json()["route"])


if __name__ == "__main__":
    unittest.main()
