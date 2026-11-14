# PHAROS Build Spec Final

Build in this order: clean backend → Grok Voice → camera and range sensor → full sensor integration → Jetson and arm. Inventory Jetson storage and identify the arm in parallel so hardware availability does not delay the last stage. One runnable PHAROS application owns perception, navigation, speech arbitration and arm requests. Run it on a Mac during development and on the Jetson Orin Nano for final integration.

## 1. Backend and code import

**Owner A.** Create one Python package and one local service. Start with the Brio 100 and a prerecorded input. Keep capture, inference, voice and serial I/O off the request loop. Keep only the latest frame per source. Timestamp at capture, validate freshness on every decision, and invalidate results after disconnect or source change.

| Destination | Port from the local import kit | New work |
| --- | --- | --- |
| `src/pharos/perception/` | `app/vision/{model,tracking,http_camera,capture}.py`, model manifest and three vision tests from `perception-source`. Use `visionlab/capture.py` as a reference for latest-frame processing and recovery. | One Linux-compatible UVC adapter keyed by configured device identity, and one W11 adapter. Normalize to the existing observation contract. Convert normalized boxes to decoded-frame pixel coordinates explicitly. Add stable scene and bottle cues. |
| `src/pharos/navigation/` | `visionlab/{navigation,routes}.py`, standard/noisy replay fixtures and route tests from `navigation-memory-source`. | Live location adapter, surveyed waypoints, projection into local metres, and route hold/resume when fixes go stale. Extract replay-independent logic and keep replay labeled. |
| `src/pharos/interaction/` | `visionlab/{commands,store}.py` and memory tests. Use `service.py`, `search.py` and benchmark fixtures as references for intent routing, stability and false-positive reporting. | One catalog for keys/bottle and their explicit SQLite placements. Use a demo tag for personal keys and the common detector for bottles. Handle a live sighting and a saved place as distinct results. Keep the experimental keyring worker out of the required runtime. |
| `firmware/w11/`, `firmware/range/` | Camera preparation script plus its vendor notes. Range extraction starts from the sensor-only feedback implementation and controller tests. | Keep only the camera capture path and one USB range protocol. Update generator and reader together to use `X-PHAROS-Frame-Age-Us`. Drop hosted upload, haptics and earlier application layers. |

The import kit lives at `work/pharos-import-review/` beside the review output directory. It is a local review copy of exact source files with commit IDs and checksums in `PROVENANCE.local.txt`. Port in small changes, fix imports and fixture paths, and adapt tests that depend on the previous application entry point. Use PHAROS names for package paths, headers and settings. Keep upstream attribution where required. Confirm reuse and redistribution permissions before adding prior code, vendor examples or model assets to a submission. Keep credentials, private captures, real location traces and databases out of Git. Model weights are acquired separately, pinned by checksum, cached before the demo, and tested on the actual Linux ARM64 image. Verify the chosen ONNX runtime and CPU performance before adding acceleration.

Repo layout for implementation

```text
src/pharos/{api,coordinator,contracts}.py
src/pharos/{perception,navigation,interaction,arm}/
firmware/{w11,range}/
clients/location-ios/
config/{demo,bench}.example.json
tests/{fixtures,integration}/
models/manifest.json
docs/PHAROS_Build_Spec_Final.md
```

### Service contract

| Boundary | Contract |
| --- | --- |
| Camera → detector | `source=head/table, frame_id, captured_monotonic_ms, size_px, image`. Camera age is mandatory for live wireless cues. Use local USB for table vision. Head capture and depth mount are separate sources. |
| Detector → coordinator | `Observation` with source, mode, frame ID, capture time, pixel boxes, class, confidence, and table fixture/zone status when applicable. “What's ahead?” uses fresh stable detections and camera-relative direction. If input expires, return unavailable. |
| Client → service | `GET /v1/health`, `GET /v1/status`, `POST /v1/location`, `POST /v1/intent`. Location is authenticated on the local link. Trusted local controls alone can approve, enable, reset or directly stop bench motion. A tool call and a typed intent pass through the same validation. |
| Intent → result | `request_id, mode, kind, args` → `status, text, data`. Status distinguishes live observation, saved placement, unavailable, pending approval, fault and completion. Requests never contain raw arm commands. |
| Sensor → cue policy | Timestamp and health plus valid left/center/right path states of `clear, blocked, unknown`. Alert events carry priority and expiry. Stop, sensor faults and obstacle warnings preempt route and conversational speech. |

Backend gate: both camera modes can be mocked, known-image detection passes, ten live head frames decode, keys and bottle placements survive restart, stale frames emit no live cue, replay finishes and dropout holds progression. Test actual demo bottle left/center/right twice and test absent/ambiguous scenes. A visual tag provides a scoped keyring demo. Capture-only throughput is not speech latency.

### Live GPS and clearance policy

**GPS.** Use a foreground iPhone Core Location sender on the local link. Send `seq, lat_deg, lon_deg, horizontal_accuracy_m, fix_time_utc, age_at_send_ms`; the receiver adds monotonic receipt time. Keep precise location enabled for the test. Reject invalid or repeated fixes and hold on stale/inaccurate data, implausible jumps, missing coverage or ambiguous parallel paths. Record measured timing and accuracy outdoors. Start with a five-second freshness ceiling and tune the accuracy/corridor gates from the checked route. If transport delay cannot be bounded, hold. Project live fixes and checked waypoints into the same local metre frame. Require consecutive accepted fixes for a turn and arrival; never use quiet GPS as obstacle clearance. On a sighted, supervised outdoor route with one clear turn, require two correct runs and a disconnect that produces no further turn cues. Use labeled replay indoors if live fixes are poor. USB GNSS via `gpsd` is a later phone-free option. [Core Location](https://developer.apple.com/documentation/CoreLocation/getting-the-current-location-of-a-device) · [GPS accuracy](https://www.gps.gov/gps-accuracy) · [GPSD client](https://www.gpsd.io/client-howto.html)

**Obstacles.** The single ultrasonic sensor gives a forward proximity warning. A verified near reading triggers “Stop, obstacle ahead.” No echo, timeout or disconnection becomes unknown and holds navigation. Add a borrowed USB stereo depth camera for directional cues. Fix its height, angle and forward orientation for the demo. Project depth to three marked body-width paths, including the near swept area and floor coverage. Check minimum range and invalid-pixel behavior. A sector is clear only when the tested path is covered by current valid measurements and free of obstructions. Use several consecutive valid frames and measure latency. Offer “Left side open” or “Right side open” after Stop only when the corresponding path is verified; require explicit resume after a hold. Flat supervised lane only. Test left-only, right-only, both blocked, narrow obstacle, invalid depth and unplugging twice each. Any wrong-side cue disables direction for the demo. If only a compact multizone ToF board is available, use directions only if measured coverage passes the same tests. [Stereo depth setup](https://docs.luxonis.com/hardware/platform/depth/configuring-stereo-depth) · [Multizone ToF limitations](https://www.st.com/resource/en/datasheet/vl53l5cx.pdf)

## 2. Grok Voice

**Owner B.** Run the Grok adapter next to the local service. Use the xAI Realtime WebSocket with `grok-voice-latest` and a server-side `XAI_API_KEY`. Start with push-to-talk, mono 24 kHz PCM16, manual audio commit, and bounded playback. If a browser connects directly later, use ephemeral client credentials. Send user speech while push-to-talk is active. Keep frames and raw location out of the voice session by default. [xAI speech-to-speech](https://docs.x.ai/developers/model-capabilities/audio/speech-to-speech) · [Realtime reference](https://docs.x.ai/developers/rest-api-reference/inference/voice)

- Expose only validated tools for `describe_scene`, `find_item(item)`, `remember_item(item, place)`, `start_route(route_id)`, `pause_route`, `request_skill(skill_id, item)` and `stop`. The route ID and skill ID must exist locally. Explicitly spoken placement commands can write memory; camera sightings cannot.
- On `response.function_call_arguments.done`, validate the current push-to-talk turn and schema, deduplicate call ID, invoke the local service, return `function_call_output`, then request continuation after all outputs for the turn. Reject stale calls after cancellation, reconnect or mode changes. Consume at most one motion request per turn. Grok receives status such as “awaiting approval.” Only the local service can report observed completion.
- Safety cues use preloaded local audio and interrupt Grok playback. Reject expired replies and avoid listening to playback. Cloud failure leaves local typed controls, stop and sensor warnings available. Use local offline push-to-talk with a restricted vocabulary for the internet-disconnected Jetson arm acceptance run. Grok Voice is the connected experience.
- Gate with typed calls first, then a real mic/speaker. Verify “what's ahead,” “where are my keys,” and “bring the bottle” against a fake arm. Check duplicate calls, dropped network, Stop during playback and prompts trying to issue arbitrary motion. No cloud tool can approve or enable a move.

## 3. Camera and ultrasonic bench

**Owner C.** Use the **W11 as the first wearable camera**, **Brio 100 as the first arm camera**, and **Pico as a sensor controller if there is no separate ESP32 DevKit**. Choose the Pi Zero as a camera fallback if it streams sooner or more reliably than the W11.

| Hardware | Bring-up decision |
| --- | --- |
| W11 ESP32-S3 | Check label, sensor and expansion board against the vendor profile. Use the supplied camera connector/ribbon with power off. Solder only verified headers or power connections called for by the board. The prepared OV3660 matching build uses `esp32:esp32:XIAO_ESP32S3:PSRAM=opi`; compile against the reviewed core version, then flash only the positively identified port. Pull VGA JPEGs on private Wi-Fi. Check orientation and capture age. [W11 vendor guide](https://wiki.meshnology.com/W11/W11_ESP32S3_Mini_Module/) |
| Raspberry Pi Zero | Verify the exact Zero variant, CSI port, camera model and correct narrow Zero ribbon. If it is a wireless model, boot Raspberry Pi OS, run `rpicam-hello --list-cameras`, then prove stable local streaming with age metadata. Original Zero without Wi-Fi needs a separate link. The Zero adds an OS, storage and power setup, so choose it only if it beats the W11 in actual bring-up. [Zero hardware](https://www.raspberrypi.com/documentation/computers/zero.html) · [Camera hardware](https://www.raspberrypi.com/documentation/accessories/camera.html) |
| Raspberry Pi Pico | Use USB serial for ultrasonic data if needed. Use board-specific GPIO and firmware. The standard Raspberry Pi CSI ribbon camera belongs on the Zero. [Pico documentation](https://www.raspberrypi.com/documentation/microcontrollers/pico-series.html) |
| Brio 100 | Reserve the known-working USB RGB feed for the fixed table fixture. It can serve as the head camera proxy during early testing. It does not produce measured depth. |

**Wiring.** Identify the ultrasonic module first. For a standard 5 V HC-SR04, use a documented 5 V rail, common GND, and a verified divider or level shifter on ECHO before the 3.3 V GPIO. Check the peak at the actual supply voltage with a scope or validate the divider using a controlled DC source. Verify the TRIG input accepts the controller's output; buffer if needed. The previous DevKit firmware uses GPIO18/19 for TRIG/ECHO on its matching board only. Choose documented free pins for the Pico, and keep the range sensor off W11 camera pins. Power off for soldering, inspect for bridges and verify continuity and rail polarity before power-up. Connect camera and range separately before combining. Do not join independent supply rails.

**Range protocol.** USB serial JSON lines `{v,seq,valid,range_mm}`. Timestamp receipt, reject non-increasing sequence numbers and malformed values, time out on missing updates, and reset sequence tracking only on an explicit reconnect. Start with 100 ms sampling and a bounded echo timeout for the verified module. Calibrate against a flat target at 30/60/100 cm plus a no-echo case. Confirm sensor unplugging pauses route cues. Run the W11 or Pi feed for 60 seconds, log measured frame age, and verify stale images stop generating live cues after disconnect. Use known-good USB if neither wireless path qualifies.

## 4. Jetson and vision-guided arm

**Owner D, with a spotter.** Verify the exact Orin Nano carrier, UEFI, target storage, USB mic/speaker, stable USB arm port and separate motor supply. For the official developer kit, the installer USB writes to microSD or NVMe. Boot and run CPU vision and offline audio before GPU optimization. Verify Waveshare SKU, firmware and elbow motion before assuming commands or limits. Raspberry Pi and W11 can supply sensor data. The Jetson owns skill execution. [NVIDIA quick start](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/quick_start.html) · [Waveshare teaching reference, if M2-S is confirmed](https://www.waveshare.com/wiki/RoArm-M2-S_Step_Recording_and_Reproduction)

**Selection by where the user points their head.** Use the glasses view as a pointing input. On “pick up what I'm pointing at,” hold a narrow center region and require a single stable supported target over multiple fresh frames. Speak what was selected and allow cancel, repeat or a named target. This uses head direction, with no eye tracker or visual confirmation required from the user. In the first demo, the Brio must independently see that same supported target in one marked pickup jig. Use one bottle and only one candidate. If glasses and table disagree, decline. For two zones later, add visibly distinct tags or a validated mapping and require unique cross-camera association. Never transfer a pixel from a moving head camera into robot coordinates.

**Teach one skill.** `bottle_to_tray` uses a light empty bottle, fixed jig, tray, and a rigid bolted or clamped stand. Secure the Brio so the fixture, jig and two reference marks stay fixed. Record joint-space poses at verified speeds: park → approach → grasp → lift → tray → release → retreat → park. Teaching records fixture-specific waypoints and verifies swept clearances. Computer vision confirms the right item and jig before movement. Use known contact geometry from the jig. A calibrated tabletop plane can select additional taught zones later; arbitrary 3D grasping requires additional sensing and testing.

**Execution.** Start disabled. The coordinator requires a live fixed-camera observation with matching fixture ID, fresh reference marks and target evidence, a healthy arm, and a local spotter approving the exact pending task before expiry. Keep the measured joint/effort limits in fixture config. Send one bounded step at a time through exclusive USB serial. Check documented feedback or validated dwell, monitor camera/serial health, and halt on a stall, timeout, fixture shift or disconnect. Clear all pending motion on stop and require manual recovery. Test the independent physical power cut-off and drop/sag behavior unloaded. Keep the participant outside the swept area until power/motion is disabled and the spotter clears the tray. Wearable fit is unpowered with actuator supply and powered tether disconnected.

## Integration gates

| By elapsed hour | Required evidence |
| --- | --- |
| H4 | A ports core detection, recall and replay paths. B completes typed intent → fake arm pending approval. C confirms board labels, sensor voltage and camera connector. D confirms arm model, Jetson storage and stand materials. |
| H10 | Real camera → detection → query and route replay on Mac. One live outdoor phone track reaches the backend. Grok mic → local tool → audible response against fake arm. |
| H16 | W11 or Zero and ultrasonic pass separate bench checks, then run together. Repeat GPS walkthrough. Enable directional cues only after depth coverage and the lane test pass. Use USB camera and forward warning if needed. |
| H22 | Jetson cold boot, Linux camera and mic/speaker, arm status, qualified stand/cut-off and unloaded safe path. First locally approved lift and tray deposit. |
| H28 | Grok-driven request on Jetson with laptop disconnected. Repeat with internet disconnected using offline voice. Head-point selection names the target and table vision checks the jig. |
| H33–H36 | Freeze hardware, configuration and code. Record at least 9/10 successful approved bottle picks with zero unsafe motion. Demonstrate zero moves with wrong or stale target, expired approval, stop, reconnect and accidental speech. Save logs with commit, config, device IDs and latency. Preflight again if setup moves. |

Demo order: outdoor GPS turn and dropout, indoor obstacle warning or qualified side cue, scene plus keys/bottle questions, then voice → head-directed selection → Brio confirmation → spotter approval → tray. Record real passes and label fallback modes. If Jetson voice fails, use a local manual request and report the voice gap. If hardware safety qualification fails, keep actuator power isolated and show a simulated arm.
