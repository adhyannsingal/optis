from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from optis.api import create_app
from optis.perception.announcements import ChairAnnouncement


CHAIR = {"label": "chair", "stable": True, "position": "center"}


class ChairAnnouncements(unittest.TestCase):
    def test_stable_centered_chair_announces_once_then_rearms(self):
        tracker = ChairAnnouncement()
        tracker.update([{**CHAIR, "stable": False}], 100)
        self.assertIsNone(tracker.snapshot(100))
        tracker.update([{**CHAIR, "position": "left"}], 200)
        self.assertIsNone(tracker.snapshot(200))
        tracker.update([CHAIR], 300)
        event = tracker.snapshot(400)
        self.assertEqual(event["text"], "Chair ahead.")
        tracker.update([CHAIR], 1100)
        self.assertEqual(tracker.snapshot(1300)["event_id"], event["event_id"])
        self.assertIsNone(tracker.snapshot(1800))
        tracker.update([], 1900)
        self.assertIsNone(tracker.snapshot(1900))
        tracker.update([CHAIR], 2300)
        self.assertNotEqual(tracker.snapshot(2300)["event_id"], event["event_id"])
        tracker.update([], 2400)
        self.assertIsNone(tracker.snapshot(2400))

    def test_phone_can_fetch_announcements_without_a_gps_fix(self):
        class Camera:
            def start(self, record):
                pass

            def close(self):
                pass

            def announcement(self):
                return "ready", {"event_id": "test", "text": "Chair ahead.", "expires_in_ms": 1000}

        with tempfile.TemporaryDirectory() as directory:
            app = create_app(database=Path(directory) / "test.sqlite3", token="web", location_token="phone", camera=Camera())
            with TestClient(app) as client:
                path = "/v1/vision/announcement"
                self.assertEqual(client.get(path).status_code, 401)
                self.assertEqual(client.get(path, headers={"Authorization": "Bearer web"}).status_code, 401)
                response = client.get(path, headers={"Authorization": "Bearer phone"})
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertEqual(response.json()["announcement"]["text"], "Chair ahead.")
