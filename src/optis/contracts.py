"""v1 table-observation gate for the simulated cup fixture."""
from collections import deque
from copy import deepcopy
import math


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class TableGate:
    def __init__(self, fixture_id="mock-cup-fixture-v1"):
        self.fixture_id = fixture_id
        self.frames = deque(maxlen=2)
        self.last_id = -1
        self.error = "stale_frame"

    def clear(self):
        self.frames.clear()
        self.error = "stale_frame"

    def validate(self, observation, now_ms, *, require_cup=True):
        if not isinstance(observation, dict):
            return "stale_frame"
        if (type(observation.get("v")) is not int or observation.get("v") != 1 or observation.get("mode") != "replay"
                or observation.get("source") != "table" or observation.get("fixture_id") != self.fixture_id
                or observation.get("reference_ok") is not True):
            return "fixture_invalid"
        seen = observation.get("seen_ms")
        if not finite(seen) or not 0 <= now_ms-seen <= 750:
            return "stale_frame"
        size = observation.get("size_px")
        if (not isinstance(size, list) or len(size) != 2
                or not all(type(v) is int and v > 0 for v in size)):
            return "fixture_invalid"
        detections = observation.get("detections")
        if not isinstance(detections, list):
            return "fixture_invalid"
        cups = []
        for detection in detections:
            if not isinstance(detection, dict):
                return "fixture_invalid"
            score, box = detection.get("confidence"), detection.get("bbox_xyxy_px")
            if (not finite(score) or not 0 <= score <= 1 or not isinstance(box, list) or len(box) != 4
                    or not all(finite(v) for v in box)
                    or not 0 <= box[0] < box[2] <= size[0] or not 0 <= box[1] < box[3] <= size[1]):
                return "fixture_invalid"
            if detection.get("label") == "cup" and score >= .7:
                cups.append(detection)
        if not require_cup:
            return None
        if len(cups) > 1:
            return "ambiguous"
        if not cups:
            return "no_target"
        if cups[0].get("pickup_zone") != "pickup_a":
            return "wrong_zone"
        return None

    def update(self, observation, now_ms):
        if observation is None:
            self.clear()
            return
        error = self.validate(observation, now_ms)
        frame_id = observation.get("frame_id") if isinstance(observation, dict) else None
        if type(frame_id) is not int or frame_id < 0:
            error = "fixture_invalid"
        if error:
            self.frames.clear()
            self.error = error
            if type(frame_id) is int:
                self.last_id = max(self.last_id, frame_id)
            return
        if frame_id <= self.last_id:
            # Repeated polling is not a second distinct frame. An older frame
            # invalidates admission rather than restoring earlier good evidence.
            if frame_id < self.last_id:
                self.clear()
            return
        self.last_id = frame_id
        self.frames.append(deepcopy(observation))
        self.error = None

    def check(self, now_ms):
        if self.error:
            return self.error
        if len(self.frames) != 2:
            return "stale_frame"
        for observation in self.frames:
            if error := self.validate(observation, now_ms):
                return error
        return None
