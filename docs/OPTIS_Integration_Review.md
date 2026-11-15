# Optis integration review and revised build plan

## What changes

The first plan protects tabletop retrieval but puts navigation outside the main build and treats the Jetson as interchangeable with a laptop. Optis needs three deliverables: route guidance with live GPS, scene and personal-item guidance, and a voice-triggered arm cycle running on the Jetson Orin Nano. Keep the fixed tabletop fixture, stand, spotter approval and physical cut-off from the [bench runbook](OPTIS_Bench_and_Demo.md).

Prove three short flows at judging. Show an automatic GPS route cue on a physically checked outdoor segment, camera-relative scene and object answers, and a Jetson-operated bottle transfer. Show an automatic obstacle warning and, only if separate side clearance is verified, a left/right cue on a supervised mock lane. Run navigation and arm handling as separate user modes. The wearable fit demo remains unpowered. The fallback for each flow stays independent so a failed GPS or glasses integration cannot block the arm.

## Components to prioritize

| Component | Build around | Work still required |
| --- | --- | --- |
| Object detection and camera input | YOLOv8n ONNX preprocessing/decoding, bottle/scene classes, temporal tracking, and timestamped W11 capture if the actual glasses board matches. One detector serves scene and bottle queries. | Obtain the model artifact matching the manifest, Linux ARM runtime and camera/audio hardware. Existing Mac webcam throughput does not establish Jetson performance. Use USB UVC as the first device. |
| Route checkpoint and proximity logic | Checked-route and explicit hold/resume behavior as reference. Reuse independent proximity warning firmware if the actual controller and range sensor match. | Existing routes require explicit checkpoint confirmation. One forward sensor cannot choose a side. No live GPS source, path planner, or side-clearance validation was found. Do not start by deploying FastAPI, React, phased backends, or the hosted camera path. |
| Intent parsing and item memory | Small intent parser, explicit SQLite placements and timestamped recall across restart. Add Optis intents at the boundary. Reuse the device-free tests. | Report saved placement and live sighting separately. Add Linux mic/speaker adapters. The Swift front end, native camera helper and macOS `say` paths are Mac demo components. |
| Route replay and item search | Route progression logic, stale-fix/detour/arrival guards and noisy replay tests. Keyring stability gate and benchmark format are reusable test references. | The current route provider accepts simulated local metres. Add a separate live provider and real fixes. Experimental YOLOE keyring benchmarks use synthetic/generated inputs. Validate live personal-key identification on new footage or use a tag. |
| Optis · [v1 retrieval contract](OPTIS_Interfaces.md) | Fresh table frames, verified fixture, named poses, stop/recovery, request and approval tokens. | Implement model-specific USB adapter and verify reported elbow behavior. Run locally on Jetson before polishing other features. |

Record the provenance of any reused code and assets. Before including prior work in a submission, verify organizer eligibility rules, contributor permission, and applicable licenses. Keep a standalone path using permitted public dependencies and fresh Optis adapters.

## Essential paths

### 1. GPS route guidance

Use the phone as a position source for the sprint. First prove a real outdoor fix and a stable connection. Attach timestamp, latitude/longitude, horizontal accuracy, and receipt time. Include fix age measured on the phone and reject out-of-order samples. Measure transport delay on the test link and treat freshness as unknown when the two clocks cannot be compared reliably. Match fixes to one physically checked, low-complexity route with one turn and a destination area. For a small route, convert WGS84 fixes and waypoints to a shared local metre frame explicitly. Advance only on consecutive fresh, sufficiently accurate fixes with corridor/turn evidence. Stale data, off-route movement and ambiguous parallel paths hold progress. Confirm arrival with distinct good fixes. Manual pause/stop work throughout. Do not infer travel heading from a nearly stationary phone. Report heading unavailable if the route decision depends on it. A supervised outdoor recording and a clearly labeled noisy replay cover judging when indoor GPS is poor. Live routing from arbitrary origins, indoor positioning and crossing instructions are later work. [GPS.gov accuracy](https://www.gps.gov/gps-accuracy)

### 2. Scene awareness, side cues and item questions

- **“What’s in front of me?”** Summarize one or two fresh, stable detections with camera-relative direction. “Chair ahead in view” describes image position. Report distance only if the sensing and object association were measured. Rate-limit unsolicited narration.
- **Automatic obstacle behavior.** For a center obstruction, say “Stop, obstacle ahead.” Only offer a side after a stationary or slow supervised mock-lane check shows a traversable strip on that side. Use verified depth or independently ranged sectors covering the candidate corridor, including its width and near path. A missing reading is unknown. A single ray per side or empty detection boxes cannot establish corridor clearance. If both sides are blocked, stale, or unobserved, hold at “Stop” and suppress directional cues. The MVP directional test uses a flat controlled lane and no stairs, curbs, crossings or unsupervised blind walking. Route turns and local obstruction cues use distinct phrasing.
- **“Where are my keys?”** Recall an explicit placement with its timestamp. For a live personal-item demo, use a small known visual tag on the demo keyring and call it a tagged item. If using generic detection, speak “possible keyring,” never ownership. An absent, stale or ambiguous live match yields “I don’t see it now” plus saved placement if present.
- **“Where is my bottle?”** Give a fresh camera-relative direction or the last explicit location. A guide camera sighting never grants movement. Only the fixed table camera can qualify the bottle on the taught pickup jig.

### 3. Voice-controlled arm and standalone Jetson

- Confirm Orin Nano carrier, storage, firmware and supply. Boot and verify a USB microphone, local speaker, UVC camera and stable arm serial identification before adding acceleration or W11. Separate arm power from Jetson power. Test a Linux ARM64 offline push-to-talk recognizer with a small vocabulary and offline spoken replies or local WAV clips. One candidate is Vosk, subject to a real install and timing check on the Jetson image. Mac speech and a typed CLI are development fallbacks. They do not satisfy the standalone voice gate. [NVIDIA quick start](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/quick_start.html) · [Vosk supported platforms](https://alphacephei.com/vosk/install)
- Teach one named skill, `bottle_to_tray`, by capturing and validating waypoints on the rigid stand. A second taught task is stretch. If RoArm-M2-S is confirmed, vendor step recording can help capture poses. Keep execution stepwise and interruptible from the Jetson. Do not start an opaque multi-step loop whose stop behavior is unverified. [Waveshare step recording](https://www.waveshare.com/wiki/RoArm-M2-S_Step_Recording_and_Reproduction)
- Push-to-talk “Bring the bottle to the tray” creates a request. The Jetson binds it to the named, allowlisted skill and checks the correct fixture, fresh table-zone evidence and arm status. A local spotter checks the area and approves once. Voice Stop cancels on a best-effort basis. A software stop control and independent physical cut-off remain available regardless of audio, network or process state. Unknown phrases, ASR self-trigger, missing approval, sensor failure or disconnection leave motion disabled or stop the active sequence. Reset requires deliberate manual recovery. Follow the [bench runbook](OPTIS_Bench_and_Demo.md).
- Acceptance starts at cold boot with the laptop and internet disconnected. The Jetson handles mic input, speech output, fixture detection, approval UI, serial, and logs locally. A phone may supply GPS in navigation mode. Arm mode is independent of the phone, network and laptop.

## Integration contracts and repository scope

Keep one coordinator, one camera owner per source, one actor writing serial, and one audio scheduler. Use typed in-process events on the Jetson. Only the phone/optional glasses need a local network boundary. Keep existing retrieval contract field names. Add:

| Boundary | Fields and behavior |
| --- | --- |
| Phone → location adapter | `lat_deg, lon_deg, horizontal_accuracy_m, fix_time, age_at_send_ms, received_monotonic_ms, source, seq`. Delay and fix quality must be checked. No fix is an explicit state. Replay events use a distinct source and a virtual clock. |
| Proximity/depth → cue policy | `observed_monotonic_ms, frame_id, left, center, right, sensor_status`. Each sector is `blocked, clear, unknown`. `clear` requires verified coverage of the candidate walk corridor. Presence and absence of detections never alone set clearance. |
| Mic/keyboard → coordinator | `intent_id, source, kind, target`. Allowlist `scene, find, remember, start_route, pause, stop, retrieve` plus existing local controls. Mode changes clear stale events and pending arm tokens. Speech cannot enable, approve, reset or send coordinates. |
| Coordinator → announcer | `mode, priority, text, created_ms, expires_ms`. Urgent Stop/obstacle and fault cues preempt routine navigation or scene narration. Cancel old cues on mode changes. Push-to-talk excludes TTS overlap and old transcripts. |

Keep the existing `src/optis` plan and add `navigation/` for route/location and `perception/clearance.py` for the directional cue gate. Add replay inputs under `tests/fixtures/`, acceptance logs outside source by default, and a single documented headless Jetson launch path. Use `navigation` and `bench` modes with separate controls. The bench sensor and arm contracts take precedence for motor decisions.

## Four owners and revised checkpoints

| Owner | First independent task | Handoff |
| --- | --- | --- |
| A · Jetson and perception | Boot from verified target media. Prepare ONNX assets and CPU camera smoke on an available host in parallel. | Jetson Linux/device report, live head and fixed table adapters, one bottle/scene vision baseline and measured latency. |
| B · Arm and safety | Confirm model/firmware and elbow, install stand and cut-off with D, build fake USB adapter and teach the one valid skill. | Verified fixture and joint bounds, approved pick sequence and stop/recovery results. |
| C · Navigation and clearance | Capture real phone fixes outdoors, mark one route, exercise the route engine against recorded fixes and simulated stale feeds. Identify available side-coverage hardware. | Real/replay modes, obstacle and side-coverage evidence, decision on live side cue by H12. |
| D · Voice, item memory and integration | Run typed/mocked intents and store/retrieve. Prepare offline mic/speaker loop and submission. Spot for B during live work. | One launch path, arbitration and approval, evidence matrix, demo media and submission. |

| By | Gate and cut decision |
| --- | --- |
| H0–H4 | Assign owners, confirm reuse eligibility, acquire Jetson storage and mic, record exact hardware. Demonstrate a full mock voice-intent → approval → fake arm flow plus saved item recall and stale route replay. |
| H7 | Prove Jetson boot and USB enumeration, real outdoor GPS fix, and safe bench startup prerequisites. If Jetson is blocked after a focused setup attempt, keep development on laptop while A continues standalone bring-up. If GPS has no accepted fix, prepare labeled replay. |
| H12 | Run offline mic-to-intent-to-audible-response on Jetson with fake arm. Run route turn and dropout with live/recorded real fixes. Prove side-coverage sensing or commit the live lane demo to Stop-only. B and D qualify table geometry, motion envelope and cut-off. |
| H18 | First complete Jetson-controlled table retrieval with typed/local request acceptable for this checkpoint. One successful lift, drop and park. C records supervised GPS route and navigation hold tests. |
| H24 | Cold boot and run voice-to-arm with laptop and internet disconnected. Run scene/bottle direction and saved keys in the same coordinator. Choose and record the best passing tier separately for GPS, side cues, item finding and arm. |
| H27 | Submit initial entry before the initial deadline. Disclose existing work, real device evidence and simulated segments accurately. |
| H29–H33 | Finish acceptance, capture backup clips and freeze hardware layout/release. Skip second skills, open-vocabulary queries, ESP32 upgrades or custom detector training until all required gates are stable. |
| H35–H36 | Submit before the final deadline. Rehearse using the qualified mode and fallbacks. |

H0 is the start of the build. Treat submission targets as internal buffers and confirm the actual portal deadlines.

## Acceptance and evidence

| Claim | Pass before using it in the demo | Fallback |
| --- | --- | --- |
| GPS route cue | Two supervised traversals of one checked segment with the correct turn and arrival area. Stale/inaccurate/removed fixes never advance the route. Include measured fix accuracy and a wrong-turn case. | Verified field recording, or labeled replay with no live GPS claim. |
| Automatic side cue | Run blocked center with verified left-only, right-only, both blocked, and sensor dropout/unknown, at least twice each. Correct side cues only in covered clear cases, zero false directional cues in the test set. Stop suppresses queued route audio. | Measured center warning, or labeled software replay if physical sensing is unavailable. |
| Front scene and item answers | Test verified left/center/right twice, absent and stale video, lookalike keys, and saved recall after restart. Report live cues within 2 s of recognized request if measured. Persist only explicit placements for the demo. | Saved recall and confirmed tagged-key demo. Label the camera proxy or unavailable live search. |
| Standalone voice and arm | On Jetson with laptop/internet disconnected, actual mic and audible reply, one command creates one request, unknown/noisy speech never causes actuation, no approval means zero moves, and the [benchmark](OPTIS_Bench_and_Demo.md#acceptance-matrix) reaches at least 9/10 picks with zero unsafe motion. Record SHA, actual host and device IDs. | If voice fails but Jetson completes the authorized cycle, show Jetson manual trigger and label the voice gap. If Jetson fails, show a separately qualified supervised laptop bench demo or simulation. If stand/cut-off fails, isolate power. |

Planning evidence includes device-free tests of saved recall across restart and simulated route dropout, recovery, and arrival. Cameras, live GPS, microphones, Jetson execution, and arm hardware still require Optis acceptance tests.
