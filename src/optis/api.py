"""Local Optis backend. Hardware motion is unavailable in this build."""
from contextlib import asynccontextmanager
from base64 import b64encode
from datetime import UTC, datetime, timedelta
import hmac
import json
import math
import os
from pathlib import Path
import stat
from threading import Lock
from time import monotonic
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat
from starlette.concurrency import run_in_threadpool

from .interaction.store import Store
from .interaction.voice import AUDIO_FILES, MAX_AUDIO_BYTES, SpeechQueue, VoiceError, XaiVoice, command
from .navigation.location import PhoneFix, PhoneRoute, fix_age, usable_origin
from .navigation.navigation import Navigation, Thresholds as NavigationThresholds
from .navigation.routes import DEFAULT_ROUTE, FixtureRouteProvider, RouteError
from .navigation.valhalla import Destination, RoutingUnavailable, Valhalla


class WalkDestination(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=300)
    lat: FiniteFloat = Field(ge=-85, le=85)
    lon: FiniteFloat = Field(ge=-180, le=180)


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=128)
    kind: Literal["scene", "find", "remember", "forget", "start_route", "next", "pause", "resume", "stop", "retrieve", "find_destination", "walk_to", "navigate_to", "choose_destination", "recalculate"]
    item: Literal["keys", "phone", "bottle"] | None = None
    place: str | None = Field(default=None, min_length=1, max_length=300)
    route_id: str | None = None
    query: str | None = Field(default=None, min_length=1, max_length=200)
    destination: WalkDestination | None = None
    choice: int | None = Field(default=None, ge=1, le=6)


def item_result(camera, item=None):
    _, observation = camera.snapshot() if camera else ("disabled", None)
    if not observation:
        return "unavailable", "Camera view unavailable.", None
    candidates = observation["detections"]
    if item:
        labels = {"keys": "keyring", "phone": "cell phone", "bottle": "bottle"}
        candidates = camera.keyring_snapshot() if item == "keys" else [
            detection for detection in candidates if detection["label"] == labels[item]
        ]
        if len(candidates) > 1:
            return "ambiguous", f"I see more than one possible {labels[item]}.", None
    stable = [d for d in candidates if d["stable"]]
    if not stable:
        return "not_seen", "I don't see it now." if item else "No stable objects detected in view.", None
    objects = stable[:2]
    text = "; ".join(f"{d['label']}, {d['position']} of camera view" for d in objects)
    return "live_observation", text + ".", objects


def create_app(*, database=None, token=None, checked_route=None, camera=None, voice=None, voice_key_file=None, router=None, location_token=None, frontend=None):
    lock = Lock()
    navigation = None
    live_source = None
    route_generation = 0
    planned_fix_seq = -1
    pending_destinations = None
    recent_sightings = {}
    forgotten_at = {}
    last_fix = None
    recording = False

    def active_voice():
        if voice or not voice_key_file:
            return voice
        try:
            with voice_key_file.open() as secret:
                metadata = os.fstat(secret.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
                    return None
                key = secret.read(4096).strip()
        except OSError:
            return None
        return XaiVoice(key) if key else None

    speech = SpeechQueue(active_voice)

    def publish(cue):
        if cue and cue.get("speech"):
            if cue["status"] in {"weak_signal", "missed_turn", "detour", "turn", "arrived"}:
                speech.clear()
            speech.submit(cue)
        return cue

    def route_map():
        if not navigation or not navigation.live or not live_source or not live_source.mapped_paths:
            return None
        return {
            "active": navigation.active, "paused": navigation.paused,
            "name": navigation.route["name"], "step": navigation.step,
            "position": live_source.accepted_position,
            "destination": live_source.mapped_paths[-1][-1],
            "paths": live_source.mapped_paths,
            "maneuvers": [{"index": index, "instruction": instruction, "end": path[-1]}
                          for index, (instruction, path) in enumerate(zip(
                              navigation.route["instructions"], live_source.mapped_paths))],
        }

    def record(item, seen_ms):
        with lock:
            now = monotonic()
            age = now - seen_ms / 1000
            if not recording or not 0 <= age <= 1 or seen_ms <= forgotten_at.get(item, -1):
                return
            previous = recent_sightings.get(item)
            if previous is not None and seen_ms - previous < 2000:
                return
            app.state.store.sight(item, camera.camera_name, datetime.now(UTC) - timedelta(seconds=age))
            recent_sightings[item] = seen_ms

    @asynccontextmanager
    async def lifespan(app):
        nonlocal recording
        app.state.store = Store(database)
        recording = True
        if camera:
            camera.start(record)
        try:
            yield
        finally:
            with lock:
                recording = False
            if camera:
                camera.close()
            app.state.store.close()

    app = FastAPI(title="Optis", lifespan=lifespan)

    def authorize(authorization, *, expected=token, alternate=None):
        if not authorization or not any(
            hmac.compare_digest(authorization.encode(), f"Bearer {value}".encode())
            for value in (expected, alternate) if value
        ):
            raise HTTPException(401, "A valid local Optis token is required.")

    @app.get("/camera", include_in_schema=False)
    def camera_page():
        return FileResponse(Path(__file__).with_name("camera.html"), media_type="text/html")

    @app.get("/v1/camera/preview")
    def camera_preview(authorization: str | None = Header(default=None)):
        authorize(authorization)
        state, observation, jpeg = camera.preview() if camera else ("disabled", None, None)
        return JSONResponse(
            {"state": state, "observation": observation, "image": b64encode(jpeg).decode() if jpeg else None},
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/v1/vision/announcement")
    def vision_announcement(authorization: str | None = Header(default=None)):
        authorize(authorization, expected=location_token or token)
        state, event = camera.announcement() if camera else ("disabled", None)
        return JSONResponse({"camera_state": state, "announcement": event}, headers={"Cache-Control": "no-store"})

    @app.get("/v1/health")
    def health():
        return {"status": "ok", "camera": camera.snapshot()[0] if camera else "disabled",
                "live_route_configured": checked_route is not None,
                "live_route_id": checked_route.route_id if checked_route else None,
                "pedestrian_routing_configured": router is not None,
                "voice_configured": active_voice() is not None, "arm": "disabled"}

    def current_fix():
        if not last_fix:
            return None, None
        packet, received, age_at_receipt = last_fix
        return packet, age_at_receipt + monotonic() - received

    @app.get("/v1/status")
    def status(authorization: str | None = Header(default=None)):
        authorize(authorization)
        with lock:
            route_status = navigation.last_state if navigation else None
            if navigation and navigation.live and navigation.active and not navigation.paused:
                latest = navigation.last_timestamp if navigation.last_timestamp is not None else navigation.started_at
                if latest is not None and monotonic() - latest > navigation.thresholds.max_age:
                    route_status = publish(navigation.weak_signal())
            location_status = None
            packet, age = current_fix()
            if packet:
                ready = usable_origin(packet, age)
                location_status = {
                    "seq": packet.seq, "horizontal_accuracy_m": packet.horizontal_accuracy_m,
                    "age_seconds": round(age, 1),
                    "usable": ready, "ready": ready,
                }
            return {"route": route_status, "route_map": route_map(), "location": location_status,
                    "audio": speech.status(), "arm": "disabled"}

    @app.get("/v1/navigation/audio")
    def navigation_audio(authorization: str | None = Header(default=None)):
        authorize(authorization)
        item = speech.take()
        if item:
            item["audio"] = b64encode(item["audio"]).decode()
        return JSONResponse({"cue": item}, headers={"Cache-Control": "no-store"})

    @app.post("/v1/location")
    def location(packet: PhoneFix, authorization: str | None = Header(default=None)):
        nonlocal last_fix
        authorize(authorization, alternate=location_token)
        if packet.fix_time_utc.utcoffset() is None:
            raise HTTPException(422, "Fix timestamp must include a UTC offset.")
        with lock:
            age = fix_age(packet, datetime.now(UTC))
            if age is not None and (last_fix is None or packet.fix_time_utc > last_fix[0].fix_time_utc):
                last_fix = packet, monotonic(), age
            if router and (not navigation or not navigation.active or not navigation.live):
                return {"status": "fix_received", "text": "Phone fix received. Choose a walking destination."}
            if not live_source and not checked_route:
                return {"status": "fix_received", "text": "Phone fix received. No checked route is configured."}
            if not navigation or not navigation.live:
                raise HTTPException(409, "Start the checked route before sending live fixes.")
            try:
                return publish(live_source.update(navigation, packet))
            except ValueError as error:
                raise HTTPException(422, str(error)) from error

    def plan_walk(request):
        nonlocal navigation, live_source, route_generation, planned_fix_seq, pending_destinations
        if not request.destination:
            raise HTTPException(422, "Choose a walking destination.")
        selected = Destination(**request.destination.model_dump())
        with lock:
            packet, age = current_fix()
            if not packet or not usable_origin(packet, age):
                raise HTTPException(409, "Waiting for a fresh, accurate GPS fix.")
            if request.kind == "recalculate" and packet.seq <= planned_fix_seq:
                raise HTTPException(409, "Wait for a new fresh phone GPS fix before recalculating.")
            origin = packet.lat_deg, packet.lon_deg
            route_generation += 1
            generation = route_generation
        try:
            paths, instructions = router.plan(origin, selected)
            route = PhoneRoute({
                "id": "valhalla", "name": selected.name,
                "waypoints": [paths[0][0], *(path[-1] for path in paths)],
                "instructions": instructions,
            }, mapped_paths=paths)
        except RoutingUnavailable as error:
            raise HTTPException(503, str(error)) from None
        except RouteError as error:
            raise HTTPException(422, str(error)) from None
        with lock:
            if generation != route_generation:
                raise HTTPException(409, "That route request was superseded.")
            packet, age = current_fix()
            if not usable_origin(packet, age) or math.hypot(
                *route.project(packet.lat_deg, packet.lon_deg)
            ) > NavigationThresholds.corridor:
                raise HTTPException(409, "Stay near the start of the mapped path and try again with a fresh GPS fix.")
            route.reset()
            navigation = Navigation(route.geometry, live=True)
            live_source = route
            pending_destinations = None
            planned_fix_seq = packet.seq
            speech.clear()
            return dict(request_id=request.request_id, **publish(navigation.start()))

    @app.post("/v1/intent")
    def intent(request: Intent, authorization: str | None = Header(default=None)):
        nonlocal navigation, live_source, route_generation, pending_destinations
        authorize(authorization)
        if request.kind in {"find_destination", "walk_to", "navigate_to", "choose_destination", "recalculate"}:
            if not router:
                raise HTTPException(503, "Valhalla pedestrian routing is not configured.")
            if request.kind == "walk_to":
                return plan_walk(request)
            if request.kind == "recalculate":
                with lock:
                    if not live_source or not live_source.mapped_paths or not navigation or not navigation.active:
                        raise HTTPException(409, "Start a mapped walking route before recalculating.")
                    lat, lon = live_source.mapped_paths[-1][-1]
                    destination = WalkDestination(name=navigation.route["name"], lat=lat, lon=lon)
                return plan_walk(request.model_copy(update={"destination": destination}))
            if request.kind == "choose_destination":
                with lock:
                    candidates = pending_destinations
                    if not candidates or monotonic() > candidates[1] or not request.choice or request.choice > len(candidates[0]):
                        raise HTTPException(409, "Destination choices expired. Ask for the place again.")
                    selected = candidates[0][request.choice - 1]
                    pending_destinations = None
                return plan_walk(request.model_copy(update={"destination": WalkDestination(
                    name=selected.name, lat=selected.lat, lon=selected.lon)}))
            if not request.query or not request.query.strip():
                raise HTTPException(422, "Enter a place name, address, or coordinates.")
            with lock:
                packet, age = current_fix()
                origin = (packet.lat_deg, packet.lon_deg) if packet and usable_origin(packet, age) else None
            try:
                matches = router.search(request.query.strip(), origin)
            except RoutingUnavailable as error:
                raise HTTPException(503, str(error)) from None
            except RouteError as error:
                raise HTTPException(422, str(error)) from None
            if not matches:
                if request.kind == "navigate_to":
                    with lock:
                        pending_destinations = None
                return dict(request_id=request.request_id, status="destination_not_found",
                            text="No match in the local map. Try a fuller name, address, or coordinates.", data=[])
            if request.kind == "navigate_to" and len(matches) == 1:
                selected = matches[0]
                return plan_walk(request.model_copy(update={"destination": WalkDestination(
                    name=selected.name, lat=selected.lat, lon=selected.lon)}))
            if request.kind == "navigate_to":
                with lock:
                    pending_destinations = (matches, monotonic() + 60)
            if len(matches) == 1:
                text = f"Found {matches[0].name}. Select it when GPS is ready."
            else:
                names = [match.name for match in matches]
                options = [f"{index}: {match.name}" + (
                    f" at {match.lat:.5f}, {match.lon:.5f}" if names.count(match.name) > 1 else "")
                           for index, match in enumerate(matches, 1)]
                text = f"Found {len(matches)} matches: " + "; ".join(options) + ". Say choose first or choose second, or select one in the dashboard."
            return dict(request_id=request.request_id, status="destinations", text=text,
                        data=[dict(name=match.name, lat=match.lat, lon=match.lon) for match in matches])
        with lock:
            store = app.state.store
            kind, item = request.kind, request.item
            data = None
            if kind in {"find", "remember", "forget"} and item is None:
                raise HTTPException(422, "Choose keys, phone, or bottle.")
            if kind == "remember":
                if not request.place or not request.place.strip():
                    raise HTTPException(422, "Provide a saved place.")
                data = store.remember(item, request.place.strip())
                status_code, text = "saved_placement", f"Saved {item} at {data['location']}."
            elif kind == "forget":
                forgotten_at[item] = monotonic() * 1000
                recent_sightings.pop(item, None)
                placement = store.forget(item)
                sighting = store.clear_sightings(item)
                status_code, text = ("forgotten", f"Cleared memory for {item}.") if placement or sighting else (
                    "not_found", f"No memory for {item}.")
            elif kind in {"scene", "find"}:
                status_code, text, data = item_result(camera, item if kind == "find" else None)
                if kind == "find" and status_code in {"unavailable", "not_seen"}:
                    sighting = store.last_seen(item)
                    placement = store.recall(item)
                    if sighting:
                        seen = datetime.fromisoformat(sighting["seen_at"]).astimezone()
                        label = {"keys": "a keyring", "phone": "a phone", "bottle": "a bottle"}[item]
                        when = seen.strftime("%I:%M:%S %p").lstrip("0")
                        if seen.date() != datetime.now().astimezone().date():
                            when = f"{seen.strftime('%b %d, %Y')} at {when}"
                        text += f" I last saw {label} at {when} in the {sighting['camera']} view."
                        status_code, data = "last_seen", sighting
                    elif placement:
                        text += f" You saved {placement['location']} as the location for {item}."
                        status_code, data = "saved_placement", placement
            elif kind == "start_route":
                if request.route_id in {"standard", "noisy"}:
                    fixture = DEFAULT_ROUTE if request.route_id == "standard" else DEFAULT_ROUTE.with_name("noisy_walk.json")
                    navigation = Navigation(FixtureRouteProvider(fixture).get_route("du-bois-library"))
                    live_source = None
                elif checked_route and request.route_id == checked_route.route_id:
                    checked_route.reset()
                    navigation = Navigation(checked_route.geometry, live=True)
                    live_source = checked_route
                else:
                    raise HTTPException(404, "Unknown route. Use standard, noisy, or the configured checked route.")
                route_generation += 1
                speech.clear()
                result = publish(navigation.start())
                return dict(request_id=request.request_id, **result)
            elif kind in {"next", "pause", "resume"} and navigation:
                if kind == "pause":
                    route_generation += 1
                    speech.clear()
                if kind == "resume" and navigation.live and navigation.paused:
                    live_source.last_good = None
                method = {"next": navigation.next_event, "pause": navigation.pause, "resume": navigation.resume}[kind]
                if kind == "resume":
                    speech.clear()
                return dict(request_id=request.request_id, **publish(method()))
            elif kind == "stop":
                route_generation += 1
                pending_destinations = None
                speech.clear()
                if navigation:
                    navigation.stop()
                status_code, text = "stopped", "Stopped."
                publish({"status": "stopped", "speech": text, "data": {"step": None}})
            elif kind == "retrieve":
                status_code, text = "arm_disabled", "Arm execution is unavailable in this build."
            else:
                status_code, text = "route_inactive", "Start a route first."
            return {"request_id": request.request_id, "status": status_code, "text": text, "data": data}

    @app.post("/v1/voice")
    async def ask_voice(request: Request, authorization: str | None = Header(default=None)):
        authorize(authorization)
        with lock:
            voice_generation = route_generation
        adapter = active_voice()
        if not adapter:
            raise HTTPException(503, "Set XAI_API_KEY on the Optis server to enable voice.")
        media_type = request.headers.get("content-type", "").split(";")[0].lower()
        if media_type not in AUDIO_FILES:
            raise HTTPException(415, "Record WebM, MP4, or WAV audio.")
        audio = bytearray()
        async for chunk in request.stream():
            if len(audio) + len(chunk) > MAX_AUDIO_BYTES:
                raise HTTPException(413, "Recording is too long.")
            audio.extend(chunk)
        if not audio:
            raise HTTPException(422, "Recording is empty.")
        try:
            transcript = await run_in_threadpool(adapter.transcribe, bytes(audio), media_type)
        except VoiceError as error:
            raise HTTPException(502, str(error)) from None
        fields = command(transcript)
        result = {"status": "unknown_command", "text": "Try asking what’s ahead, where your keys are, or to walk to a place."}
        if fields:
            try:
                with lock:
                    cancelled = voice_generation != route_generation
                if cancelled:
                    result = {"status": "stopped", "text": "That voice request was cancelled."}
                else:
                    result = await run_in_threadpool(intent, Intent(request_id=str(uuid4()), **fields), authorization)
            except HTTPException as error:
                result = {"status": "command_unavailable", "text": str(error.detail)}

        result["transcript"] = transcript
        if result["status"] in {"route_started", "route_resumed", "route_paused", "stopped"}:
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        try:
            spoken, mime = await run_in_threadpool(adapter.speak, result["text"])
            with lock:
                if voice_generation == route_generation:
                    result.update(audio=b64encode(spoken).decode(), audio_type=mime)
        except VoiceError as error:
            result["voice_error"] = str(error)
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    if frontend:
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")

    return app


def from_environment():

    camera = None
    if source := os.getenv("OPTIS_CAMERA"):
        from .perception.worker import HeadCamera

        model = Path(os.environ["OPTIS_MODEL"])
        manifest = json.loads(Path(os.environ.get("OPTIS_MODEL_MANIFEST", "models/manifest.json")).read_text())
        keyrings = None
        if checkpoint := os.getenv("OPTIS_KEYRING_MODEL"):
            from .perception.keyrings import KeyringSearch

            keyrings = KeyringSearch(Path(checkpoint))
        camera = HeadCamera(source, model, manifest["onnx_sha256"], keyrings=keyrings,
                            camera_name=os.getenv("OPTIS_CAMERA_NAME", "head camera"))
    route = PhoneRoute(json.loads(Path(path).read_text())) if (path := os.getenv("OPTIS_ROUTE")) else None
    token = os.environ.get("OPTIS_TOKEN")
    if not token:
        raise RuntimeError("Set OPTIS_TOKEN before starting the backend.")
    key = os.getenv("XAI_API_KEY")
    key_file = os.getenv("OPTIS_XAI_KEY_FILE")
    router = Valhalla(url, os.getenv("OPTIS_PLACES_INDEX")) if (url := os.getenv("OPTIS_VALHALLA_URL")) else None
    return create_app(database=os.getenv("OPTIS_DB"), token=token, checked_route=route, router=router,
                      location_token=os.getenv("OPTIS_LOCATION_TOKEN"), frontend=os.getenv("OPTIS_FRONTEND"), camera=camera,
                      voice=XaiVoice(key) if key else None, voice_key_file=Path(key_file) if key_file else None)
