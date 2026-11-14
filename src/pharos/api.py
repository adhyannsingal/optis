"""Local PHAROS backend. Hardware motion is unavailable in this build."""
from contextlib import asynccontextmanager
import hmac
import json
import os
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .interaction.store import Store
from .navigation.location import PhoneFix, PhoneRoute
from .navigation.navigation import Navigation
from .navigation.routes import DEFAULT_ROUTE, FixtureRouteProvider


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=128)
    kind: Literal["scene", "find", "remember", "forget", "start_route", "next", "pause", "resume", "stop", "retrieve"]
    item: Literal["keys", "bottle"] | None = None
    place: str | None = Field(default=None, min_length=1, max_length=300)
    route_id: str | None = None


def item_result(camera, item=None):
    _, observation = camera.snapshot() if camera else ("disabled", None)
    if not observation:
        return "unavailable", "Camera view unavailable.", None
    stable = [d for d in observation["detections"] if d["stable"]]
    if item:
        # Generic keyring matches do not establish personal identity.
        stable = [d for d in stable if item == "bottle" and d["label"] == item]
        if len(stable) > 1:
            return "ambiguous", "I see more than one bottle.", None
    if not stable:
        return "not_seen", "I don't see it now." if item else "No stable objects detected in view.", None
    objects = stable[:2]
    text = "; ".join(f"{d['label']}, {d['position']} of camera view" for d in objects)
    return "live_observation", text + ".", objects


def create_app(*, database=None, token=None, checked_route=None, camera=None):
    lock = Lock()
    navigation = None

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(database)
        if camera:
            camera.thread.start()
        try:
            yield
        finally:
            if camera:
                camera.close()
            app.state.store.close()

    app = FastAPI(title="PHAROS", lifespan=lifespan)

    def authorize(authorization):
        if not token or not authorization or not hmac.compare_digest(
            authorization.encode(), f"Bearer {token}".encode()
        ):
            raise HTTPException(401, "A valid local PHAROS token is required.")

    @app.get("/v1/health")
    def health():
        return {"status": "ok", "camera": camera.snapshot()[0] if camera else "disabled",
                "live_route_configured": checked_route is not None, "arm": "disabled"}

    @app.get("/v1/status")
    def status(authorization: str | None = Header(default=None)):
        authorize(authorization)
        with lock:
            route_status = navigation.last_cue if navigation else None
            if navigation and navigation.live and navigation.active and not navigation.paused:
                current = navigation.tick(monotonic())
                if current["status"] == "weak_signal":
                    route_status = current
            return {"route": route_status, "arm": "disabled"}

    @app.post("/v1/location")
    def location(packet: PhoneFix, authorization: str | None = Header(default=None)):
        authorize(authorization)
        with lock:
            if not checked_route:
                result = {"status": "fix_received", "text": "Phone fix received. No checked route is configured."}
                if packet.fix_time_utc.utcoffset() is None:
                    raise HTTPException(422, "Fix timestamp must include a UTC offset.")
                return result
            if not navigation or not navigation.live:
                raise HTTPException(409, "Start the checked route before sending live fixes.")
            try:
                return checked_route.update(navigation, packet)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error

    @app.post("/v1/intent")
    def intent(request: Intent, authorization: str | None = Header(default=None)):
        nonlocal navigation
        authorize(authorization)
        with lock:
            store = app.state.store
            kind, item = request.kind, request.item
            data = None
            if kind in {"find", "remember", "forget"} and item is None:
                raise HTTPException(422, "Choose keys or bottle.")
            if kind == "remember":
                if not request.place or not request.place.strip():
                    raise HTTPException(422, "Provide a saved place.")
                data = store.remember(item, request.place.strip())
                status_code, text = "saved_placement", f"Saved {item} at {data['location']}."
            elif kind == "forget":
                deleted = store.forget(item)
                status_code, text = ("forgotten", f"Removed saved placement for {item}.") if deleted else (
                    "not_found", f"No saved placement for {item}.")
            elif kind in {"scene", "find"}:
                status_code, text, data = item_result(camera, item if kind == "find" else None)
                if kind == "find" and status_code != "live_observation":
                    placement = store.recall(item)
                    if placement:
                        text += f" Last confirmed at {placement['location']} ({placement['confirmed_at']})."
                        status_code, data = "saved_placement", placement
            elif kind == "start_route":
                if request.route_id in {"standard", "noisy"}:
                    fixture = DEFAULT_ROUTE if request.route_id == "standard" else DEFAULT_ROUTE.with_name("noisy_walk.json")
                    navigation = Navigation(FixtureRouteProvider(fixture).get_route("du-bois-library"))
                elif checked_route and request.route_id == checked_route.route_id:
                    checked_route.reset()
                    navigation = Navigation(checked_route.geometry, live=True)
                else:
                    raise HTTPException(404, "Unknown route. Use standard, noisy, or the configured checked route.")
                result = navigation.start()
                return dict(request_id=request.request_id, **result)
            elif kind in {"next", "pause", "resume"} and navigation:
                if kind == "resume" and navigation.live and navigation.paused:
                    checked_route.last_good = None
                method = {"next": navigation.next_event, "pause": navigation.pause, "resume": navigation.resume}[kind]
                return dict(request_id=request.request_id, **method())
            elif kind == "stop":
                if navigation:
                    navigation.stop()
                status_code, text = "stopped", "Stopped."
            elif kind == "retrieve":
                status_code, text = "arm_disabled", "Arm execution is unavailable in this build."
            else:
                status_code, text = "route_inactive", "Start a route first."
            return {"request_id": request.request_id, "status": status_code, "text": text, "data": data}

    return app


def from_environment():

    camera = None
    if source := os.getenv("PHAROS_CAMERA"):
        from .perception.worker import HeadCamera

        model = Path(os.environ["PHAROS_MODEL"])
        manifest = json.loads(Path(os.environ.get("PHAROS_MODEL_MANIFEST", "models/manifest.json")).read_text())
        camera = HeadCamera(source, model, manifest["onnx_sha256"])
    route = PhoneRoute(json.loads(Path(path).read_text())) if (path := os.getenv("PHAROS_ROUTE")) else None
    token = os.environ.get("PHAROS_TOKEN")
    if not token:
        raise RuntimeError("Set PHAROS_TOKEN before starting the backend.")
    return create_app(database=os.getenv("PHAROS_DB"), token=token, checked_route=route, camera=camera)
