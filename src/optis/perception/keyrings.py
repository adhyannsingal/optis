"""Open-vocabulary keyring search on the newest available camera sample."""

import logging
from pathlib import Path
from threading import Condition, Thread
from time import monotonic

from .model import Detection
from .tracking import Tracker

LOGGER = logging.getLogger(__name__)


class KeyringSearch:
    def __init__(self, model: Path):
        self.model = model.resolve()
        self.condition = Condition()
        self.pending = None
        self.result = None
        self.generation = 0
        self.stopping = False
        self.thread = Thread(target=self.run, name="keyring-search", daemon=True)

    def offer(self, frame, seen_ms, record):
        with self.condition:
            self.pending = (frame, seen_ms, record, self.generation)
            self.condition.notify()

    def snapshot(self):
        with self.condition:
            if self.result and 0 <= monotonic() * 1000 - self.result[0] <= 1000:
                return self.result[1]
            return []

    def clear(self):
        with self.condition:
            self.generation += 1
            self.pending = self.result = None

    def close(self):
        with self.condition:
            self.stopping = True
            self.condition.notify()
        self.thread.join(timeout=2)

    def run(self):
        try:
            import torch
            from ultralytics import YOLOE

            if not self.model.is_file():
                raise ValueError("Provide a local YOLOE checkpoint prepared for keyring search.")
            torch.set_num_threads(2)
            model = YOLOE(str(self.model))
            if list(model.names.values()) != ["keyring"]:
                raise ValueError("The local YOLOE checkpoint must have one class named keyring.")
            tracker = Tracker()
            previous_generation = -1
            while True:
                with self.condition:
                    self.condition.wait_for(lambda: self.stopping or self.pending is not None)
                    if self.stopping:
                        return
                    frame, seen_ms, record, generation = self.pending
                    self.pending = None
                if generation != previous_generation:
                    tracker = Tracker()
                    previous_generation = generation
                if monotonic() * 1000 - seen_ms > 1000:
                    tracker = Tracker()
                    continue
                boxes = model.predict(frame, device="cpu", imgsz=640, conf=.25, verbose=False)[0].boxes
                height, width = frame.shape[:2]
                detections = [Detection("keyring", score, (x1 / width, y1 / height, x2 / width, y2 / height))
                              for (x1, y1, x2, y2), score in
                              zip(boxes.xyxy.tolist(), boxes.conf.tolist())]
                objects, _ = tracker.update(detections, seen_ms)
                matches = [dict(
                    label="keyring", position=obj["position"], confidence=obj["score"],
                    bbox_xyxy_px=[v * scale for v, scale in zip(obj["box"], (width, height, width, height))],
                    stable=tracker.tracks[obj["track_id"]]["count"] >= 2,
                ) for obj in objects]
                with self.condition:
                    if self.stopping or generation != self.generation or monotonic() * 1000 - seen_ms > 1000:
                        continue
                    self.result = seen_ms, matches
                if len(matches) == 1 and matches[0]["stable"]:
                    record("keys", seen_ms)
        except Exception:
            LOGGER.exception("Keyring search stopped")
