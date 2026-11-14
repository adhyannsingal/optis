# PHAROS v1 system contracts

D owns the interface definitions. A, B, C and D agree on field names and fake fixtures before writing live adapters. The baseline uses Python calls and JSON-serializable data inside one process. If an ESP32 camera is used, its JPEG/MJPEG stream terminates at the capture adapter. The arm stays on a local, exclusively owned serial connection.

## Capture and observations

A provides `latest(source) -> Observation | None`. The two logical sources are `head` (guidance) and `table` (retrieval gate). Source roles identify the calibration and intended use. On the single-camera fallback, A may derive both observations from the same physical frame. Mock/replay mode labels all observations `replay` and runs only with the fake arm.

```json
{
  "v": 1,
  "mode": "live",
  "source": "table",
  "frame_id": 42,
  "seen_ms": 123456,
  "size_px": [640, 480],
  "fixture_id": "table-a-r1",
  "reference_ok": true,
  "detections": [
    {
      "label": "bottle",
      "confidence": 0.92,
      "bbox_xyxy_px": [288, 148, 350, 284],
      "pickup_zone": "pickup_a"
    }
  ]
}
```

- `seen_ms` is host monotonic milliseconds sampled at capture/dequeue before inference. Compare on the same host only. Capture keeps the newest frame, discards backlog, and marks a timed-out or unverifiably delayed stream unavailable. Fixed table capture uses local USB for the live bench path. Record receive-to-inference timing for wireless head video.
- `frame_id` increases per source during one process lifetime. After restart clear observations, enable and pending tokens. Empty `detections` means a fresh frame with no candidate. `None` means input unavailable.
- Box coordinates are top-left-origin pixel edges in the decoded frame, ordered `x_min,y_min,x_max,y_max`, within `size_px`. Confidence is finite in [0,1], with the bench threshold chosen from observed positives/negatives (start tuning at 0.70 for a scored detector). For a deterministic fiducial a pass may report 1.0. The selected method and threshold are recorded in config. For guidance, split the normalized box center into left, center, right thirds after correcting any preview mirroring.
- `fixture_id` is the active calibration ID and is null for `head`. `reference_ok` is true only for a table frame whose two fixed reference marks pass the recorded location tolerances. `pickup_zone` is `pickup_a` only if the known bottle/marker anchor falls inside the configured zone, otherwise null. Measure the anchor against the jig with clean positives and off-jig negatives. Head observations always have a null zone. If marks, lighting or placement are inconclusive, withhold the gate.
- Admission requires two distinct recent table frames in a row with exactly one qualifying bottle, same live source, fixture, and zone, good reference marks, and both aged 0–750 ms. A second bottle-like candidate in the pickup region or ambiguity invalidates the gate. Demo tolerance is limited by the physical jig and validated reference/anchor tolerances, not a free-space pixel-to-robot conversion. The operator visually confirms bottle seating, tray and clear area. No visually estimated coordinate becomes an arm command.

## Interaction and lifecycle

C provides requests from bounded voice grammar or keyboard and an `announce(event)` sink for audio/text. D accepts `submit(intent, label=None) -> Status`, `approve(task_id) -> Status`, `stop() -> Status` and `status() -> Status`. The local console separates user input from the spotter-only approve/enable/reset controls. Voice has no approve, enable, reset or jog command. Stop is available to the operator/spotter independently of speech recognition.

| Intent | Input | Result |
| --- | --- | --- |
| `find` | “Find my bottle” / Find button with `label=bottle` | Speak/name the fresh head-relative direction and refresh the selected class for 30 s. Ask to look again when absent, ambiguous or stale. |
| `retrieve` | “Bring it to the tray” / Retrieve button | Uses the current class selection and fresh table evidence. Creates one pending task with a unique ID and 10 s approval deadline. If evidence is missing, prompt to check the jig. |
| `approve` | Spotter-only local action with the exact displayed task ID | Recheck live observations, selection, fixture, arm health, software enable and deadline under the coordinator lock. Operator/safety spotter check clear setup visually. Consume token before issuing the first step. |
| `stop` | Operator or spotter local Stop control | Cancel pending and queued motion, latch stopped, signal adapter immediately and use physical cut-off if movement persists or the system is unresponsive. |
| `reset` / `enable` | Spotter-only local actions | Separate manual recovery and enable after verification. Clear stale selection and pending tokens. New motion always needs a new retrieval and approval. |

```json
{"v":1,"state":"awaiting_approval","task_id":"pick-0007","mode":"bench","label":"bottle","zone":"pickup_a","fixture_id":"table-a-r1","stage":null,"code":null}
```

States are `disabled`, `idle`, `awaiting_approval`, `executing`, `complete`, `stopped` and `faulted`. Start disabled. Enabling grants no movement by itself. In mock mode every arm method is fake. Only an explicitly selected bench mode with matching fixture, model and calibrated pose plan may enable the real adapter. One task holds the arm at a time. Reject repeat/late/mismatched approvals and duplicate busy requests. An admission failure drops the pending task and stays ready for a fresh request. User instructions, detector results and model output cannot select raw vendor commands.

Publish state/stage transitions and refusal codes to both console and a JSONL trace with host time, task ID and mode. Codes include `no_target`, `stale_frame`, `ambiguous`, `wrong_zone`, `fixture_invalid`, `needs_enable`, `busy`, `approval_expired`, `wrong_task`, `arm_timeout`, `arm_fault`, and `operator_stop`. Eye-level guidance is advisory and continues to use the head input independently of table calibration. A capture failure is voiced as unavailable rather than as a direction.

## Arm contract

B implements the same methods for fake and real adapters. Arm I/O runs off the interaction loop, with stop independently signaled and prioritized over regular commands. Only one serial owner writes to the arm. Close or physically isolate vendor tools before coordinator access.

| Call | Contract |
| --- | --- |
| `health() -> ArmStatus` | Model, firmware, connectivity, fault/stop latch, available feedback and last known pose. Read-only and time-bounded. |
| `move(task_id, pose_id, timeout_ms)` | One named taught pose via validated sequence. Reject unknown pose, invalid transition, wrong model/fixture, out-of-range joints and speed, stop latch, or timeout. |
| `grip(task_id, action, timeout_ms)` | `open\|close` at allowed stages only, using fixture-specific jaw limits. Return once confirmed by supported feedback or the validated bounded dwell policy. |
| `stop(reason)` | Latch immediately, prevent subsequent writes for normal motion, discard queued steps and signal the verified model-specific halt. Best effort through firmware. Physical power cut-off is independent. |
| `reset()` | Manual exclusive recovery to a disabled state. No automatic jog, home or retry. A separate supervised recovery action can use the verified park routine. |

All writes return `{ok, code, pose_id, elapsed_ms}`, with `pose_id` null if unknown. Sending bytes is insufficient to claim a step succeeded. Prefer verified model position/motion feedback and record its tolerance. If feedback is unavailable, only use a supervised timed sequence after dry-run validation of explicit per-stage settle times, with the spotter able to stop at any point. That mode reports task motion complete and requires separate human observation of the actual deposit. Do not claim grasp verification from elapsed time.

Pose order is `park → pre_pick → pick → close → lift → pre_drop → drop → open → retreat → park`. Preposition with gripper open before the run; home/park is checked by the operator before enable. Use raised transit poses and verify the swept path for every transition including dwell. No direct interface for arbitrary user coordinates. Use hard caps of 5 s per step and 30 s per task for this scripted demo, with shorter verified per-step values in config. If the arm needs longer at qualified speeds, revise the time budget and rerun qualification. After approach starts, freeze the taught plan. Do not track or retarget a moving bottle. If video goes stale, source faults, stop is pressed, or feedback fails mid-run, halt, latch and require manual recovery. Once the arm enters the image, normal gripper occlusion is allowed. The spotter watches continuously for people, fixture shift, stall or drops.

## Fixture configuration and logs

`bench.local.json` records `fixture_id`, camera identity/resolution and orientation, two reference mark centers and max deviations (pixels), pickup polygon/anchor rule, detection method/threshold, model/firmware, serial port parameters, joint and jaw bounds, model units/speed settings, named joint poses and allowed transitions, feedback tolerances or documented dwell, step timeouts and verified maximum test load. Use measured values and fail closed on a missing required value, ID mismatch, unsupported units, or config validation failure. B and D sign off and log the actual configuration ID. A camera, jig, arm base, or tray move invalidates it.

Trace each decision with monotonic timestamp, mode, task ID, stage, status/code, source frame ID and age, fixture ID and elapsed time where available. Track the release SHA and configuration ID alongside the trace. Record only data required for diagnostics and aggregate demo results.
