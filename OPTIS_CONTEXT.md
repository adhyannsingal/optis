# Optis — shared context for Cursor and coding agents

**Status:** Assistive prototype. This file is a handoff summary from project planning, not a live synchronization of ChatGPT messages. Refer to GitHub docs as the source of truth and update this context when the team changes decisions.

## Product
Optis explores assistive object guidance and tabletop retrieval: a seated participant requests an empty lightweight bottle, receives camera-relative audio/text guidance, requests retrieval, and a **spotter-approved**, **stand-mounted** arm moves the bottle from a marked fixed jig to a tray. A wearable fit is shown only with motor power disconnected. Do not claim a clinically validated or safe wearable powered system.

## Team workstreams
- A: perception/cameras and Jetson; `src/optis/perception/`
- B: Waveshare arm, fixture and hardware safety; `src/optis/arm/`, local bench configuration
- C: glasses, voice/keyboard input, audio/captions; `src/optis/interaction/`, `firmware/glasses/`
- D: contract and coordinator integration, tests, demo, merges; `src/optis/contracts.py`, `src/optis/coordinator.py`, `tests/`
- The ChatGPT user is leading **Figma/frontend** work and wants backend development supported here and in Cursor. Role names A–D are from the team plan; do not assume a person owns a role until confirmed.

## Implementation philosophy
1. Mock-first: work on laptop with fake arm and replay observations, with no network/GPU dependency.
2. Follow **`docs/OPTIS_Interfaces.md`** for canonical exact payloads and timing. Do not replace with a generic REST design.
3. A single Python coordinator orchestrates interfaces. An HTTP or WebSocket bridge for the Figma-built UI may be added as a thin boundary later, not as the control logic.
4. Adapter replacements: replay → live capture; fake arm → documented model-specific adapter only after bench preflight.
5. Use an existing frontend home screen; design additional screens in Figma based on concrete states: disabled, idle, awaiting_approval, executing, complete, stopped, faulted.

## Critical v1 contracts (summary only)
- `latest(source) -> Observation | None`, logical sources `head` and `table`.
- Observation JSON includes `v`, `mode`, `source`, `frame_id`, `seen_ms`, `size_px`, `fixture_id`, `reference_ok`, `detections`; each detection has `label`, `confidence`, `bbox_xyxy_px`, `pickup_zone`.
- Coordinator methods: `submit(intent, label=None)`, `approve(task_id)`, `stop()`, `status()`. Spotter-only reset/enable are separate local controls.
- Status fields: `v`, `state`, `task_id`, `mode`, `label`, `zone`, `fixture_id`, `stage`, `code`.
- Fresh table admission: two distinct consecutive qualifying frames, **0–750 ms old**, same fixture/source/zone; exactly one qualifying bottle, valid fixed reference marks, correct pickup zone. No free-space camera-to-arm target coordinates.
- Retrieval creates one pending task with a **10-second** approval deadline. Recheck all gates under a coordinator lock and consume approval before first motion. Repeated, mismatched, expired or voice approvals do not move the arm.
- Arm adapter exposes `health`, `move`, `grip`, `stop`, `reset` with exclusive arm I/O.
- Taught sequence: `park → pre_pick → pick → close → lift → pre_drop → drop → open → retreat → park`. No arbitrary target pose or unverified vendor commands. Freeze plan once approach starts; stale camera, stop or feedback fault mid-run halts and latches.
- Refusal codes: `no_target`, `stale_frame`, `ambiguous`, `wrong_zone`, `fixture_invalid`, `needs_enable`, `busy`, `approval_expired`, `wrong_task`, `arm_timeout`, `arm_fault`, `operator_stop`.
- Log decisions/transitions in JSONL with monotonic timestamps, task ID, mode, relevant frame/fixture and refusal code.

## Work now
1. Implement or check `src/optis/contracts.py` validation and fake data fixtures.
2. Implement coordinator state machine with disabled startup, local enable, selection, retrieval, 10-second approval, lock, stop latch and JSONL traces.
3. Implement a fake arm adapter that records every move/grip and rejects commands when stopped.
4. Create mock CLI entry point `python -m optis.coordinator --mode mock` and fault-injection tests. Acceptance: complete mock run and invalid/expired approvals produce zero arm moves.
5. Let A/B/C integrate adapters against the contract independently. Keep bench/live arm mode disabled until hardware verification and preflight.
6. After internal contract passes, add a *thin* local frontend bridge with read-only status and scoped user controls; segregate spotter controls, restrict binding/access and maintain independent physical stop.
7. Figma handoff: produce screen contracts for Home, Live Vision (guidance), Retrieval (pending/executing/completed), and Spotter Controls (separate authority).

## Do not guess hardware facts
The plan names a Jetson Orin Nano and a Waveshare arm, but exact carrier, arm model, firmware, serial protocol, power and calibrated poses require physical verification. There is a prior elbow-control symptom, not a confirmed diagnosis. Always consult bench runbook and actual hardware team.

## References
- [Build plan](docs/OPTIS_Build_Plan.md)
- [v1 system contracts](docs/OPTIS_Interfaces.md)
- [Bench and demo runbook](docs/OPTIS_Bench_and_Demo.md)

## Working with the ChatGPT conversation
Cursor does **not** automatically receive the full ChatGPT conversation. This file captures relevant shared decisions only. For changes decided in ChatGPT later, update this file through reviewed commits so future Cursor sessions have the current context.
