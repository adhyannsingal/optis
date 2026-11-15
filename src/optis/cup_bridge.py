"""Thin HTTP bridge for the mock coordinator; spotter authority stays separate."""
import hmac
import ipaddress
import json
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from .coordinator import Coordinator
from .perception.simulated_table import SimulatedTable
from .interaction.voice import command


class SpotterAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["enable", "approve", "stop", "reset"]
    task_id: str | None = None


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal["valid", "missing", "off_mark", "ambiguous", "references", "wrong_fixture", "stale", "disconnected"]


class TypedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=200)
    request_id: str = Field(min_length=1, max_length=128)


class CupDemo:
    def __init__(self, *, coordinator=None):
        self.coordinator = coordinator if coordinator is not None else Coordinator(
            trace=lambda event: print(json.dumps(event), flush=True))
        self.table = SimulatedTable(self.coordinator)

    def start(self):
        self.table.thread.start()

    def close(self):
        self.coordinator.close()
        self.table.close()

    def result(self, status, request_id=None):
        state, code = status["state"], status["code"]
        text = (f"Simulation: cup_to_tray {state}. " +
                (f"Reason: {code}." if code else "A local spotter must approve the exact pending request within 10 seconds."
                 if state == "awaiting_approval" else "Physical arm execution remains disabled."))
        return dict(request_id=request_id, status=code or state, text=text, data=status)


def cup_router(demo, authorize, spotter_token, dispatch):
    router = APIRouter()

    def spotter(request, authorization):
        try:
            local = ipaddress.ip_address(request.client.host).is_loopback
        except (ValueError, AttributeError):
            local = False
        if not local:
            raise HTTPException(403, "Spotter controls require a local loopback connection.")
        if not spotter_token or not authorization or not hmac.compare_digest(
                authorization.encode(), ("Bearer "+spotter_token).encode()):
            raise HTTPException(401, "A separate local spotter token is required.")

    @router.post("/v1/cup-demo/request")
    def typed(body: TypedRequest, authorization: str | None = Header(default=None)):
        authorize(authorization)
        fields = command(body.text)
        if not fields or fields not in ({"kind": "retrieve", "item": "cup"}, {"kind": "stop"}):
            raise HTTPException(422, "Say: Put the cup in the tray, or Stop.")
        return dispatch(dict(request_id=body.request_id, **fields), authorization)

    @router.get("/v1/cup-demo")
    def status(authorization: str | None = Header(default=None)):
        authorize(authorization)
        coordinator = demo.coordinator
        with coordinator.lock:
            return dict(enabled=True, real_execution=False, scenario=demo.table.scenario,
                        status=coordinator.status(), events=list(coordinator.events),
                        commands=list(coordinator.arm.commands))

    @router.post("/v1/cup-demo/spotter")
    def action(body: SpotterAction, request: Request, authorization: str | None = Header(default=None)):
        spotter(request, authorization)
        if body.action == "approve":
            if not body.task_id:
                raise HTTPException(422, "Approve the exact pending task ID.")
            result = demo.coordinator.approve(body.task_id)
        else:
            result = getattr(demo.coordinator, body.action)()
        return demo.result(result)

    @router.post("/v1/cup-demo/scenario")
    def scenario(body: Scenario, request: Request, authorization: str | None = Header(default=None)):
        spotter(request, authorization)
        demo.table.set_scenario(body.scenario)
        return demo.result(demo.coordinator.status())

    return router
