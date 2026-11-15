"""One capture owner and one latest result for the guidance camera."""
import logging
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic

from .announcements import ChairAnnouncement
from .capture import encode_capture
from .http_camera import HttpCamera
from .model import OnnxDetector
from .tracking import Tracker

LOGGER = logging.getLogger(__name__)


class HeadCamera:
    def __init__(self, source, model: Path, checksum, *, keyrings=None, camera_name="head camera"):
        self.source = source
        self.model = model
        self.checksum = checksum
        self.keyrings = keyrings
        self.camera_name = camera_name
        self.record = None
        self.stop = Event()
        self.lock = Lock()
        self.observation = None
        self.jpeg = None
        self.state = "starting"
        self.chair_announcement = ChairAnnouncement()
        self.thread = Thread(target=self.run, name="head-camera", daemon=True)

    def publish(self, state, observation=None, jpeg=None):
        with self.lock:
            self.state = state
            self.observation = observation
            self.jpeg = jpeg
            if observation is not None:
                self.chair_announcement.update(observation["detections"], observation["seen_ms"])
            else:
                self.chair_announcement = ChairAnnouncement()

    def snapshot(self):
        state, observation, _ = self.preview()
        return state, observation

    def preview(self):
        with self.lock:
            if self.observation and 0 <= monotonic() * 1000 - self.observation["seen_ms"] <= 1000:
                return self.state, self.observation, self.jpeg
            return ("stale" if self.observation else self.state), None, None

    def announcement(self):
        with self.lock:
            now_ms = monotonic() * 1000
            if self.observation and now_ms - self.observation["seen_ms"] > 1000:
                return "stale", None
            return self.state, self.chair_announcement.snapshot(now_ms)

    def start(self, record):
        self.record = record
        if self.keyrings:
            self.keyrings.thread.start()
        self.thread.start()

    def keyring_snapshot(self):
        return self.keyrings.snapshot() if self.keyrings else []

    def run(self):
        frame_id = 0
        try:
            import cv2

            detector = OnnxDetector(self.model, expected_sha256=self.checksum)
            while not self.stop.is_set():
                if self.source.startswith("http://"):
                    capture = HttpCamera(self.source)
                else:
                    device = int(self.source) if self.source.isdecimal() else self.source
                    capture = cv2.VideoCapture(device)
                tracker = Tracker()
                try:
                    while not self.stop.is_set() and capture.isOpened():
                        ok, frame = capture.read()
                        if not ok:
                            break
                        seen = capture.captured_at if isinstance(capture, HttpCamera) else monotonic()
                        if seen is None:
                            self.publish("unverified_frame_age")
                            self.stop.wait(0.1)
                            continue
                        jpeg, (width, height), _ = encode_capture(frame)
                        if self.keyrings:
                            self.keyrings.offer(frame, int(seen * 1000), self.record)
                        detections = detector(jpeg)
                        if monotonic() - seen > 1:
                            tracker = Tracker()
                            self.publish("stale")
                            continue
                        frame_id += 1
                        seen_ms = int(seen * 1000)
                        objects, _ = tracker.update(detections, seen_ms)
                        boxes = []
                        for item in objects:
                            x1, y1, x2, y2 = item["box"]
                            boxes.append(dict(
                                label=item["label"], confidence=item["score"],
                                bbox_xyxy_px=[x1 * width, y1 * height, x2 * width, y2 * height],
                                position=item["position"], pickup_zone=None,
                                stable=tracker.tracks[item["track_id"]]["count"] >= 2,
                            ))
                        for label, category in (("cell phone", "phone"), ("bottle", "bottle")):
                            matches = [box for box in boxes if box["label"] == label]
                            if len(matches) == 1 and matches[0]["stable"]:
                                self.record(category, seen_ms)
                        self.publish("ready", dict(
                            v=1, mode="live", source="head", frame_id=frame_id,
                            seen_ms=seen_ms, size_px=[width, height], detections=boxes,
                            fixture_id=None, reference_ok=False,
                        ), jpeg)
                finally:
                    capture.release()
                    if self.keyrings:
                        self.keyrings.clear()
                self.publish("disconnected")
                self.stop.wait(0.5)
        except Exception:
            LOGGER.exception("Guidance camera worker stopped")
            self.publish("fault")

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
        if self.keyrings:
            self.keyrings.close()
