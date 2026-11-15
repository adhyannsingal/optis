# cup_to_tray simulated workflow handoff

Built from `docs/cup-pickup-handoff` (`3cb0bfa`). **Real execution remains disabled.**
No serial port, Waveshare SDK, teaching console, physical arm, or calibration file
is opened. Every pose is symbolic, including `mock_approach`: the one physical
candidate approach sample was neither imported nor treated as qualified.

## Run the existing /camera bench

```sh
uv sync --locked --extra test
export OPTIS_TOKEN="$(openssl rand -hex 24)"
export OPTIS_SPOTTER_TOKEN="$(openssl rand -hex 24)"
uv run python -m optis.cup_demo --web
```

Open `http://127.0.0.1:8000/camera`. Enter the user token in the existing Optis
token field; preview need not be started. In **Cup to tray — simulation only**,
the local spotter enters the separate spotter token and selects **Enable simulation**.
The user types **Put the cup in the tray** and sends it. No key, microphone,
camera or physical arm is needed. Copy the displayed pending task ID into the
spotter approval field and approve within 10 seconds. Observe the progress log.
The user token cannot approve/enable/reset or change the simulated scene.
Spotter endpoints require a loopback connection and the separate token.

Use the spotter's table-condition selector for missing, off-mark, ambiguous,
invalid-reference, wrong-fixture, stale and disconnected cases. Return to valid
and allow two fresh observations before a new request. A failure during execution
latches `faulted`; Stop latches `stopped`. Reset clears the task and returns to
`disabled`; explicit enable and a new request/approval are needed afterward.
No automatic recovery or replay of an old request occurs.

For a terminal-only demo (standard library, no FastAPI/cloud/vision dependency):

```sh
PYTHONPATH=src python3 -m optis.cup_demo
```

Commands: `spotter enable`, `user Put the cup in the tray`,
`spotter approve EXACT_TASK_ID`, `user stop`, `spotter reset`,
`scenario missing` (or another selector value), `quit`.
An explicitly scripted smoke test representing both user and spotter is:

```sh
PYTHONPATH=src python3 -m optis.cup_demo --scripted
```

Both terminal and web modes emit JSONL state/stage/refusal traces to stdout.
The web status endpoint retains the latest 200 events and fake command history.
To save a trace, redirect stdout to a **local** file outside Git. Record
`git rev-parse HEAD` with any saved test evidence.

## Contract and integration

The stage order is the v1 order:
`park → pre_pick → pick → close → lift → pre_drop → drop → open → retreat → park`.
`pre_pick` maps to the future taught `approach`, `pre_drop` to `above_tray`,
and `open` to the future taught release. There are no joint coordinates in this
implementation. Fake steps take 0.25 seconds for visible demo progress; that
value is not a physical settle criterion.

The cup handoff specializes the contract's bottle example to `cup`. Two distinct
consecutive qualifying **table** observations must match `mock-cup-fixture-v1`,
`pickup_a`, valid reference marks, and age 0–750 ms at request and approval.
Confidence is at least 0.70 for this simulated fixture. Simulated observations
are explicitly labeled `replay`; only the exact `FakeArm` class in `mock` mode is
accepted. Real/live/bench execution has no adapter and is rejected.
This simulator conservatively keeps the cup gate active at every stage; future
qualified handling of real gripper occlusion is not implemented.

`POST /v1/intent` with `kind=retrieve,item=cup` creates the pending task.
The typed `/v1/cup-demo/request` and the existing voice endpoint use the same
bounded command parser and intent handler. Speech only creates requests or Stops;
approval, enable and reset are absent from voice grammar and intent schemas.
The full canonical coordinator Status appears in the existing envelope's `data`.
`GET /v1/health` and `GET /v1/status` continue reporting physical `arm: disabled`;
`cup_simulation` is separate. Omit `OPTIS_ARM_MODE` in the normal backend to keep
the original retrieve-disabled behavior. The dedicated web command activates only
the simulated workflow. The regular factory also supports `OPTIS_ARM_MODE=mock`
with a distinct `OPTIS_SPOTTER_TOKEN`; any real/bench mode is rejected.

Checked voice work before editing: the handoff already contains the current batch
STT/TTS adapter; open frontend integration PR #10 changes frontend voice consumers,
not `src/optis/interaction/voice.py`. This branch adds only bounded cup/Stop grammar
to that module and appends controls to `/camera`; it does not rewrite audio,
frontend workspace, navigation, or key handling. Live voice was not exercised.

## Verification

- `uv run python -m unittest discover -s tests -v`: 42 tests passed, including 21
  new workflow/API tests (with multiple negative-case subtests).
- `uv run python -m optis.cup_demo --scripted`: completed all ten fake stages.
- Actual loopback HTTP smoke: typed pending → user-token approval denied → exact
  spotter approval → ten commands → complete; duplicate approval rejected; missing
  cup then refused with no additional commands. Physical arm status stayed disabled.
- `node --check src/optis/cup_demo.js` and `git diff --check`: passed.
- `uv build --wheel --out-dir /tmp/optis-cup-build`: passed; checked that the wheel
  includes the `/camera` page, simulation JavaScript and fake-arm modules.
- Temporarily inverted the approval-expiry guard: workflow tests failed; restored
  the guard and reran the passing suite.
- Browser interaction/visual QA could not run because the browser access host was
  unavailable. HTTP serving and JavaScript syntax were checked instead.

## Collect only when operator and spotter return

Keep measurements in ignored `config/*.local.json` or the existing local teaching
record; do not copy them into mock poses. Real execution stays disabled afterward
until a separately reviewed hardware adapter and qualification pass exist.

| Area | Exact data still needed |
| --- | --- |
| Fixture | Final fixture/configuration ID; clamp/stand inspection; arm-base, jig and tray placement; full swept/drop envelope and cable clearance. Recheck after the unexpected web jog. |
| Camera gate | Brio device identity, fixed resolution and orientation; two reference-mark pixel centers and allowed deviations; pickup polygon and cup anchor rule; final detector/confidence threshold. Measure positives, off-mark/ambiguous/moved-camera negatives, disconnect behavior, achieved FPS and median/p95 capture-to-observation age. Runbook target: ≥3 fresh observations/s and p95 age ≤750 ms at the jig. |
| Joint poses | Settled raw radian positions for `park`, `approach`, `pick`, `lift`, `above_tray`, `drop`, `retreat`, and return `park`, all under the final fixture ID. Recheck clearance of the existing candidate `approach`; teach every other pose. Validate each transition unloaded before a cup trial. |
| Cup/gripper | Empty cup mass, width at actual gripping height and intended grip height; measured open-jaw gap; gentle `close` and `release` raw gripper angle and load. Verify SDK angle conversion, joint order and units against raw telemetry; retain load feedback that the SDK public pose omits. Confirm a small lift holds without slipping/crushing. |
| Controller | Confirm M2-S model, firmware, exclusive USB device/serial settings, SDK 0.1.1 mapping, raw feedback timestamps, and fresh pre/post-move feedback. No console or web jog may share ownership during replay. |
| Bounds and timing | Verified joint/jaw, reduced speed/effort and load limits; per-stage feedback/settling criteria and measured durations; stall/timeout rules. Contract caps are 5 s/step and 30 s/task, not assumed achievable physical timings. |
| Stop/recovery | Measured software halt latency/residual travel; independent motor cutoff; drop/sag and startup behavior; deliberate manual recovery to disabled/verified park. Operator and spotter sign-off. |
| Outcome evidence | Unloaded transition passes, first gentle grip/short lift, tray deposit/upright result and return to park; actual success/failure counts and timing with release SHA/config ID. For the full live reliability claim, use the runbook's ≥9/10 and zero unsafe motion threshold. |
