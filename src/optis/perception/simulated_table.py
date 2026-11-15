"""Synthetic table observations only; these values are not physical calibration."""
from threading import Event, Lock, Thread
from time import monotonic

SCENARIOS = ("valid", "missing", "off_mark", "ambiguous", "references", "wrong_fixture", "stale", "disconnected")


def table_observation(frame_id, scenario="valid", now_ms=None):
    if scenario not in SCENARIOS:
        raise ValueError("Unknown simulated table scenario")
    if scenario == "disconnected":
        return None
    now_ms = monotonic()*1000 if now_ms is None else now_ms
    cup = dict(label="cup", confidence=.95, bbox_xyxy_px=[280, 160, 350, 300],
               pickup_zone=None if scenario == "off_mark" else "pickup_a")
    return dict(v=1, mode="replay", source="table", frame_id=frame_id,
                seen_ms=now_ms-1000 if scenario == "stale" else now_ms,
                size_px=[640, 480], fixture_id="wrong-fixture" if scenario == "wrong_fixture" else "mock-cup-fixture-v1",
                reference_ok=scenario != "references",
                detections=[] if scenario == "missing" else [cup, dict(cup)] if scenario == "ambiguous" else [cup])


class SimulatedTable:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.scenario = "valid"
        self.frame_id = 0
        self.lock = Lock()
        self.stop = Event()
        self.thread = Thread(target=self.run, name="simulated-table", daemon=True)

    def set_scenario(self, scenario):
        if scenario not in SCENARIOS:
            raise ValueError("Unknown simulated table scenario")
        with self.lock:
            self.scenario = scenario
            # Invalidate immediately, never let a previously clear scene approve
            # after the operator has selected a failure case.
            self.coordinator.observe(None)
            self.tick()

    def tick(self):
        self.frame_id += 1
        self.coordinator.observe(table_observation(self.frame_id, self.scenario))

    def run(self):
        while not self.stop.is_set():
            with self.lock:
                self.tick()
            self.stop.wait(.1)

    def close(self):
        self.stop.set()
        if self.thread.is_alive():
            self.thread.join(timeout=1)
