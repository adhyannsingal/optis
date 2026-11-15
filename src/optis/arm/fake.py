"""Interruptible, bounded simulation using symbolic poses, never joint coordinates."""
from threading import Event, RLock
from time import monotonic

STAGES = ("park", "pre_pick", "pick", "close", "lift", "pre_drop", "drop", "open", "retreat", "park")
POSES = {"park": "mock_park", "pre_pick": "mock_approach", "pick": "mock_pick",
         "lift": "mock_lift", "pre_drop": "mock_above_tray", "drop": "mock_drop", "retreat": "mock_retreat"}


class FakeArm:
    def __init__(self, step_seconds=.25):
        self.lock = RLock()
        self.cancel = Event()
        self.step_seconds = step_seconds
        self.commands = []
        self.connected = True
        self.fault = False
        self.fail_at = None
        self.task_id = None
        self.index = 0

    def health(self):
        with self.lock:
            return dict(model="simulated", firmware="fake-v1", connected=self.connected,
                        fault=self.fault, stopped=self.cancel.is_set(), pose_id=None)

    def move(self, task_id, pose_id, timeout_ms):
        stage = "park" if self.task_id != task_id else STAGES[self.index] if self.index < len(STAGES) else None
        if stage not in POSES or POSES[stage] != pose_id:
            return dict(ok=False, code="arm_fault", pose_id=None, elapsed_ms=0)
        return self._step(task_id, stage, pose_id, timeout_ms)

    def grip(self, task_id, action, timeout_ms):
        return self._step(task_id, action, None, timeout_ms)

    def _step(self, task_id, stage, pose_id, timeout_ms):
        began = monotonic()
        with self.lock:
            if (not self.connected or self.fault or self.cancel.is_set()
                    or not 0 < timeout_ms <= 5000):
                return dict(ok=False, code="arm_fault", pose_id=pose_id, elapsed_ms=0)
            if self.task_id != task_id:
                if stage != "park" or (self.task_id is not None and self.index != len(STAGES)):
                    return dict(ok=False, code="arm_fault", pose_id=pose_id, elapsed_ms=0)
                self.task_id, self.index = task_id, 0
            if self.index >= len(STAGES) or STAGES[self.index] != stage:
                return dict(ok=False, code="arm_fault", pose_id=pose_id, elapsed_ms=0)
            self.commands.append(dict(task_id=task_id, stage=stage, pose_id=pose_id))
            self.index += 1
        interrupted = self.cancel.wait(min(self.step_seconds, timeout_ms/1000))
        with self.lock:
            code = ("operator_stop" if interrupted else "arm_timeout" if self.step_seconds >= timeout_ms/1000
                    else "arm_fault" if not self.connected or self.fault or stage == self.fail_at else None)
            if code:
                self.fault = True
            return dict(ok=code is None, code=code, pose_id=pose_id,
                        elapsed_ms=round((monotonic()-began)*1000))

    def stop(self, reason):
        with self.lock:
            self.cancel.set()

    def reset(self):
        with self.lock:
            self.cancel.clear()
            self.fault = False
            self.task_id, self.index = None, 0
