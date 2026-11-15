# Optis bench and demo runbook

## Hardware setup

**A · Jetson.** Identify the actual module and carrier and verify the power supply and target storage. On the official Orin Nano Developer Kit, follow NVIDIA's firmware check and JetPack ISO flow. Use macOS ARM64 Etcher on the M4 to write the supported image to the USB stick after confirming the target drive. Install to verified microSD/NVMe on the Jetson. Follow the vendor firmware update path where required. On boot, record `cat /etc/nv_tegra_release`, `uname -m`, `python3 --version`, and the root mount from `findmnt /`. Run a UVC camera and CPU observation smoke test before optional accelerator work. Keep Mac/laptop venv, camera, audio and clips ready throughout. [NVIDIA quick start](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/quick_start.html) · [Firmware update](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/update_firmware.html)

**B · Waveshare.** Read the model and controller labels before using a reference manual. Record firmware, idle/startup movement, connector, voltage/current/polarity, supported serial settings and how to halt. Identify the data port with the vendor utility or a read-only status request. Verify permissions and stable USB device selection. Use only the verified supply and keep actuator and compute power independently controllable. The laptop can own serial if the Jetson is late. [Waveshare M2-S reference](https://www.waveshare.com/wiki/RoArm-M2-S) · [Waveshare M3 reference](https://www.waveshare.com/wiki/RoArm-M3)

The earlier arm setup discussion mentions a RoArm-M2-S and an elbow-up control that did not extend the arm. Treat both as setup leads. Confirm the physical label and reproduce the symptom during the supervised unloaded joint check. If the elbow cannot reach the required taught positions reliably, isolate actuator power and switch to fake-arm integration until B resolves it.

**C · Glasses.** Start with host mic, local audio, keyboard and one UVC camera. Check view orientation and usable cue latency. Timebox ESP32 bring-up after verifying board, pinout, camera and PSRAM. Use the known-good tether or stationary camera proxy if it misses H7. Demo proximity in place only if a verified sensor and local cue are available.

## Preflight for real movement

B runs the controls. D or an appointed spotter watches the whole envelope and keeps the physical motor-power cut-off within reach. Either can call stop. Pause if the area gets crowded or coverage changes.

1. With actuator power isolated, verify the arm is fastened to a rigid stand and the stand is secured to the table. Check fasteners, gripper, cable strain relief, separate supply and cut-off. Secure jig, camera and tray. Mark the full swept/drop area and keep people and loose gear outside it. Route cables away from joints. Account for sag or a dropped payload after power loss.
2. Record configuration ID, reference marks, pose limits, load and verified reduced speed/effort settings. Use the lightest stable bottle that works with the gripper. Keep tray empty and close enough for a low lift, away from table edges. Check sight lines from spotter and judge positions.
3. With the zone clear, power the arm in its documented safe startup configuration. At the lowest verified useful speed, test one joint at a time, then gripper, then each taught transition unloaded. Verify feedback or settle time and observe clearances. Add the bottle only after dry path, stop and recovery pass.
4. Exercise software stop and physical cut-off separately during a low-speed, unloaded movement with a contained drop area. Record the effect, actual residual travel and whether power loss releases joints. Establish barriers and clearance based on observed behavior. If the stop is ineffective or there is unresolved movement on startup, keep power isolated.
5. Recheck jig/marks, tray and taped boundary. Verify boot is disabled, wrong fixtures cannot enable, and stale or replay detections cannot move real hardware. Have the spotter verify the exact pending task at each trial.
6. If the setup moves, any joint stalls, hardware config changes or a safety test fails, disable and repeat affected qualification before the next powered trial. After a stop, isolate power, let motion settle, clear fault and inspect. Restore with the area clear, recover the verified park pose under supervision, then deliberately re-enable. Any previous request is invalid.

## Acceptance matrix

Record test ID, date/time, commit SHA, fixture ID, host/camera/control mode, operator/spotter, result and evidence. Run fault injection with mocks first. Repeat live safety negatives on an empty fixture only when the previous check is safe.

| ID | Owner | Procedure and pass condition |
| --- | --- | --- |
| A1 | A/C | Run the chosen live camera for 60 s, then disconnect. Record achieved rate and median/p95 observation age. On the fixed camera require at least 3 fresh detections per second at the jig and p95 age ≤750 ms. Within 1 s of a dead feed the app reports unavailable and no approval can start. |
| A2 | A/C | Place the target left, center and right in the guidance image, twice each, then remove it. Require 6/6 correct directions and unavailable or target missing for the negative. Cue and caption should appear within 2 s of a recognized or typed request. |
| A3 | A/B/D | Move bottle off jig, remove it, add an ambiguous in-zone candidate, cover a fixture mark, submit an old frame and swap fixture ID. Each trial must show the appropriate refusal with zero arm moves. Repeat with replay against the bench adapter. |
| A4 | B/D | On the empty fixture show park, expected dry path, model-specific stop, independent physical cut-off and intentional re-enable. Switch off actuator power during contained unloaded motion and verify that no powered movement continues and startup requires new clearance. Record sag and confirm it stays in the marked area. |
| A5 | C/D | Exercise valid approval exactly once, duplicate approval, wrong ID, expired approval, concurrent retrieval, and speech/keyboard without spotter approval. Only the valid request can start a sequence. |
| A6 | B/D | Inject camera/serial loss, adapter timeout and stop during execution. Verify no following step or retry is issued, visible stopped/faulted state, and no movement on reconnect or reset. Exercise physical cut-off separately if firmware cannot cancel an in-flight command. |
| A7 | All | Run 10 consecutive attempts on the frozen layout, including at least one cold start and one after power-cycle recovery. Count an attempt when retrieval is requested. Success requires correct target in tray and arm back at park with no manual intervention after approval. Require ≥9/10 and zero unsafe motion for a live end-to-end claim. Record all attempts, failure category, median seconds from approval to park for successful runs, and mode used. |
| A8 | B/C/D | Demonstrate harness fit with power and all power-capable tethers physically disconnected. Verify fit and retention with a team member or use an inert dummy/mannequin. Confirm no powered movement in the fit demo. |
| A9 | C | Optional local proximity cue. Power it locally, disconnect the network, and move a stationary-demo target across its tested trigger distance. Cue activates/clears without network; log threshold and results. |

Trial log header

```text
trial,sha,fixture_id,host,camera,intent_mode,approved,success,duration_s,failure,operator,spotter,evidence
```

Keep the calibrated layout, signed preflight, traces, recordings and release SHA available on the demo laptop. Use examples only for mock runs, and publish measured results from the actual setup.

## Judging sequence

**0:00–0:20** Explain the task from the user's perspective. Show the unpowered harness fit with a dummy or a photograph if moving the arm would disturb the bench.

**0:20–0:50** A seated teammate asks “Find my bottle.” Play the spoken cue and show matching text. State the actual camera and compute mode. Show the fixed table camera confirming the pickup zone.

**0:50–1:35** Ask “Bring it to the tray.” The spotter checks the marked area, approves locally, then watches the lift and deposit. Park and disable with the zone clear before anyone accesses the tray.

**1:35–2:00** Report the actual trial rate and timing. Show local stationary proximity warning only if qualified. Describe what the jig and static harness demonstrate.

## Fallback decisions

| Trigger | Run this |
| --- | --- |
| Jetson incomplete at H7 or image/storage is unavailable | Run the same Python configuration on laptop CPU with local assets. Keep Jetson setup off the demo path. |
| ESP32, network or audio recognition unstable at H7/H24 | USB or proxy capture and local audio/captions. Use a visible large button/keyboard if recognition drops commands. |
| Detector too slow or target is unreliable | Use the controlled fiducial and fixed jig with the same format and negative tests. Qualification is still required. |
| Full chain fails H24/H29 and stand/safety pass | Present seated guidance and the supervised taught tabletop cycle separately, using verified recovery and deliberate local authorization. If available, show a previously verified integrated run on video and report the actual live mode. |
| Arm, stand, cut-off, or booth conditions fail preflight | Demonstrate live guidance plus clearly marked simulated retrieval. Show prior qualified bench footage if available. Leave the physical arm isolated. |
| Static fit checks fail or moving the arm shifts calibration | Show an unpowered dummy or photos. Keep the working fixture assembled. |
| Venue network or power goes down | Use the laptop with cached assets or show local recorded clips. Restore the powered demo only after preflight and recovery. |

Freeze the selected judge path and backup at H33. Recheck cables and fixture marks when relocating, save both media locally, and keep the demo clip and submission receipt accessible offline.
