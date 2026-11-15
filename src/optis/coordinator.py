"""cup_to_tray state machine. This build accepts only the simulated arm."""
from collections import deque
from copy import deepcopy
from threading import RLock, Thread
from time import monotonic
from uuid import uuid4

from .arm.fake import FakeArm, POSES, STAGES
from .contracts import TableGate


class Coordinator:
    def __init__(self, arm=None, *, mode="mock", clock=monotonic, trace=None):
        if mode != "mock" or (arm is not None and type(arm) is not FakeArm):
            raise ValueError("Real execution is disabled; only FakeArm in mock mode is supported")
        self.arm = arm if arm is not None else FakeArm()
        self.clock, self.trace = clock, trace
        self.lock = RLock()
        self.gate = TableGate()
        self.worker = None
        self.events = deque(maxlen=200)
        self.state, self.task_id, self.stage, self.code = "disabled", None, None, None
        self.deadline = None
        self.selection = None
        self.selection_deadline = None
        self.requests = set()
        self._emit()

    def _status(self):
        return dict(v=1, state=self.state, task_id=self.task_id, mode="mock", label=self.selection,
                    zone="pickup_a" if self.task_id else None, fixture_id=self.gate.fixture_id,
                    stage=self.stage, code=self.code)

    def _emit(self):
        event = dict(self._status(), monotonic_ms=round(self.clock()*1000),
                     frame_ids=[frame["frame_id"] for frame in self.gate.frames],
                     frame_ages_ms=[round(self.clock()*1000-frame["seen_ms"]) for frame in self.gate.frames])
        self.events.append(event)
        if self.trace:
            self.trace(deepcopy(event))
        return self._status()

    def _expire(self):
        if self.state == "awaiting_approval" and self.clock() >= self.deadline:
            self.state, self.code, self.deadline = "idle", "approval_expired", None
            self.task_id = None
            self._emit()

    def status(self):
        with self.lock:
            self._expire()
            return self._status()

    def enable(self):
        with self.lock:
            if self.state != "disabled":
                return self._reject("needs_enable")
            if not self._healthy():
                return self._reject("arm_fault")
            self.state, self.code = "idle", None
            return self._emit()

    def reset(self):
        with self.lock:
            if self.worker and self.worker.is_alive():
                return self._reject("busy")
            self.arm.reset()
            self.state, self.task_id, self.stage, self.code = "disabled", None, None, None
            self.deadline = self.selection = self.selection_deadline = None
            self.gate.clear()
            return self._emit()

    def _healthy(self):
        try:
            health = self.arm.health()
            return health["connected"] and not health["fault"] and not health["stopped"]
        except Exception:
            return False

    def _reject(self, code):
        # Refusal does not mutate the active task (including on duplicate approval).
        result = self._status()
        result["code"] = code
        self.events.append(dict(result, monotonic_ms=round(self.clock()*1000)))
        if self.trace:
            self.trace(deepcopy(self.events[-1]))
        return result

    def observe(self, observation):
        with self.lock:
            self.gate.update(observation, self.clock()*1000)
            if self.state == "executing" and (error := self.gate.check(self.clock()*1000)):
                self._halt(error)

    def submit(self, intent, label=None, *, request_id=None):
        with self.lock:
            self._expire()
            if self.state in {"awaiting_approval", "executing"}:
                return self._reject("busy")
            if self.state not in {"idle", "complete"}:
                return self._reject("needs_enable")
            if intent == "find" and label == "cup":
                self.selection, self.selection_deadline = "cup", self.clock()+30
                self.code = self.gate.check(self.clock()*1000)
                return self._emit()
            if intent != "retrieve" or label not in {None, "cup"}:
                return self._reject("no_target")
            if request_id and request_id in self.requests:
                return self._reject("wrong_task")
            if label == "cup":
                self.selection, self.selection_deadline = "cup", self.clock()+30
            if self.selection != "cup" or self.clock() >= (self.selection_deadline or 0):
                return self._reject("no_target")
            if error := self.gate.check(self.clock()*1000):
                self.state, self.task_id, self.stage = "idle", None, None
                self.code = error
                return self._emit()
            if not self._healthy():
                return self._reject("arm_fault")
            # Bound replay protection; reset/reconnect never replays a request.
            if len(self.requests) >= 10000:
                return self._reject("busy")
            if request_id:
                self.requests.add(request_id)
            self.task_id = "cup-"+uuid4().hex
            self.deadline = self.clock()+10
            self.state, self.stage, self.code = "awaiting_approval", None, None
            return self._emit()

    def approve(self, task_id):
        with self.lock:
            self._expire()
            if self.code == "approval_expired":
                return self._reject("approval_expired")
            if self.state != "awaiting_approval" or task_id != self.task_id:
                return self._reject("wrong_task")
            error = self.gate.check(self.clock()*1000)
            if self.selection != "cup" or self.clock() >= self.selection_deadline:
                error = "no_target"
            if not self._healthy():
                error = "arm_fault"
            if error:
                self.state, self.code, self.task_id, self.deadline = "idle", error, None, None
                return self._emit()
            # Consume approval under the lock before dispatch; no second approval
            # can enqueue work. All arm I/O runs on this single background worker.
            self.deadline = None
            self.state, self.code = "executing", None
            result = self._emit()
            self.worker = Thread(target=self._execute, args=(task_id,), name="cup-to-tray", daemon=True)
            self.worker.start()
            return result

    def _halt(self, code):
        self.state = "stopped" if code == "operator_stop" else "faulted"
        self.code, self.deadline = code, None
        self.selection = self.selection_deadline = None
        self.arm.stop(code)
        return self._emit()

    def stop(self):
        with self.lock:
            return self._halt("operator_stop")

    def _execute(self, task_id):
        began = self.clock()
        try:
            for stage in STAGES:
                with self.lock:
                    if self.state != "executing" or self.task_id != task_id:
                        return
                    error = self.gate.check(self.clock()*1000)
                    if self.clock()-began >= 30:
                        error = "arm_timeout"
                    if not self._healthy():
                        error = "arm_fault"
                    if error:
                        self._halt(error)
                        return
                    self.stage = stage
                    self._emit()
                if stage in {"close", "open"}:
                    result = self.arm.grip(task_id, stage, timeout_ms=5000)
                else:
                    result = self.arm.move(task_id, POSES[stage], timeout_ms=5000)
                with self.lock:
                    if self.state != "executing":
                        return
                    if not result["ok"] or result["elapsed_ms"] > 5000 or self.clock()-began >= 30:
                        self._halt(result.get("code") or "arm_timeout")
                        return
            with self.lock:
                if self.state == "executing":
                    error = self.gate.check(self.clock()*1000)
                    if error or not self._healthy():
                        self._halt(error or "arm_fault")
                    else:
                        self.state, self.code = "complete", None
                        self._emit()
        except Exception:
            with self.lock:
                if self.state == "executing":
                    self._halt("arm_fault")

    def close(self):
        self.stop()
        if self.worker:
            self.worker.join(timeout=2)
