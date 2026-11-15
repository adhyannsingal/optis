"""One fresh announcement when a stable chair enters the center of the camera view."""

from uuid import uuid4


class ChairAnnouncement:
    def __init__(self):
        self.last_seen_ms = None
        self.event = None

    def update(self, detections, seen_ms):
        centered = any(item["label"] == "chair" and item["stable"] and item["position"] == "center"
                       for item in detections)
        if not centered:
            self.event = None
            return
        if self.last_seen_ms is None or seen_ms - self.last_seen_ms >= 1000:
            self.event = (str(uuid4()), seen_ms + 1500)
        self.last_seen_ms = seen_ms

    def snapshot(self, now_ms):
        if not self.event or self.last_seen_ms is None or not 0 <= now_ms - self.last_seen_ms <= 1000:
            return None
        event_id, expires_at = self.event
        remaining = int(expires_at - now_ms)
        if remaining <= 0:
            return None
        return {"event_id": event_id, "text": "Chair ahead.", "expires_in_ms": remaining}
