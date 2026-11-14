# PHAROS | HackUMass XIV Build Plan

**Version:** 1.0 | **Date:** November 14, 2026 | **Team:** 4 | **Build window:** 36 hours

## Project definition

**Pitch:** PHAROS is an experimental assistive system integrating camera-equipped smart glasses, edge perception, audio guidance, and a robotic manipulator to help users find and retrieve everyday objects.

**Primary workflow:** A seated user asks to find a water bottle. Glasses identify it and provide audio guidance. The user asks the robot to retrieve it. Shared object localization supplies a safe, deterministic controller, which moves a lightweight bottle from a fixed tabletop pickup point to an accessible tray. Powered autonomous manipulation is demonstrated on a rigid stand, not on a person.

## Hardware inventory

| Component | Status | Role | Initial verification |
|---|---|---|---|
| NVIDIA Jetson Nano | In hand | Edge inference and coordination | Exact SKU, OS, power, CUDA, working camera |
| Waveshare robotic arm | In hand | Physical manipulation | Exact model, supply, control interface, gripper, base holes |
| ESP32-S3 camera board | To verify | Glasses video capture | Camera and Wi-Fi stream |
| Depth camera or fixed camera | To verify | Object localization | Driver and coordinate calibration |
| Microphone, speaker, proximity sensor | To verify | Voice/audio and local obstacle feedback | I/O and latency |
| Rigid harness and emergency cutoff | To build | Mechanical fit and safety | Off-body testing first |

## MVP acceptance criteria

- Live glasses/camera stream reaches the inference computer.
- Lightweight YOLO detector identifies at least two demonstration object classes.
- System responds to a spoken request with an object name and approximate direction.
- An independently operating local proximity alert can issue a warning without network inference.
- Shared object state carries timestamp, label, confidence, camera-frame coordinates and, when available, 3D position.
- Robot responds to a tested home/stop/pose/gripper command set on a fixed test fixture.
- Camera-to-robot calibration maps a small, marked tabletop area to robot reach.
- The robot grasps a light object and delivers it to a tray with deterministic motion and a human-initiated approval step.
- Full end-to-end voice-to-retrieval demonstration runs repeatedly with an emergency power stop tested.

## Architecture

```text
Glasses camera / mic ──> Jetson perception ──> shared object state
                                             │
Voice command ──> intent interpreter ──> task coordinator
                                             │
                                             v
                             reachability + safety checks
                                             │
                                             v
                                  Waveshare arm controller
                                             │
                                             v
                                     grasp → tray placement

Local distance sensor ──> local alert actuator (independent)
```

**Inference fallback:** If the Jetson is an original Nano, use lightweight YOLO; offload larger VLM requests to a laptop or supported service. VLM output never drives servos directly.

## Team split

1. **Perception/Jetson:** OS bring-up, video capture, YOLO, inference API, detection timings.
2. **Manipulation/arm:** Independent arm testing, poses, gripper, calibration, end-effector tests, cut-off.
3. **Glasses/interaction:** ESP32 video streaming, microphone and audio, obstacle sensing, voice interface.
4. **Integration/mechanical/demo:** Shared state, workflow orchestration, rigid harness/test stand, UI, evaluation and presentation.

## 36-hour milestones

| Milestone | Hours | Deliverable | Exit gate |
|---|---|---|---|
| M0 | H0–H2 | Inventory, roles, hardware audit | Exact models and power confirmed |
| M1 | H2–H7 | Jetson, glasses and robot independently working | Camera+YOLO, robot jog, audio alert |
| M2 | H7–H12 | Shared object coordinates and robot interface | Target selected; reachable pose validated |
| M3 | H12–H18 | First autonomous table grasp | One object grasped and placed on fixed fixture |
| M4 | H18–H24 | End-to-end voice-to-retrieval | Single complete demo works |
| M5 | H24–H29 | Reliability, safety and mounting | E-stop tested, repeatable trials, fit demo unpowered |
| M6 | H29–H33 | Polish, video and pitch | Recorded fallback and quantified test results |
| M7 | H33–H36 | Freeze, rehearse and submit | Demo rehearsed; repository and submission ready |

## Feature backlog

**MVP:** Camera feed; YOLO detection; short object announcements; local obstacle warnings; voice intent; shared detection/coordinate data; robot home/stop/gripper API; grasp and tray placement; safe off-body actuation; wearable harness fit demonstration.

**Extended goals:** Spatial audio; multiple-object disambiguation; VLM scene summaries; multimodal task plans; grasp retries and verification; event logs/dashboard; more everyday objects; improved wearable packaging.

**Not in this prototype:** Fully autonomous walking navigation, body-contact grasping, feeding, or powered motion of an unvalidated arm worn by a person.

## Safety and validation

- Keep the powered arm on a stable, rigid stand or mannequin until the mounting system has been independently evaluated for human-worn motion.
- Use a physical motor-power disconnect, reduced speed, joint/workspace limits, clear pinch-zone marking and a supervised test area.
- Do not place the active gripper near the wearer’s face, neck, hands or torso.
- Test no-object homing, single-joint movements, worst-case reach, emergency power cut and safe recovery before autonomous tasks.
- Record success rate across at least ten identical object-retrieval trials, failure categories, and median task duration. Do not imply clinical validation.

## Primary demo script

1. Show the wearable harness on a person with motor power disconnected.
2. Transfer the arm to a rigid stand/mannequin and verify the physical stop.
3. User says: “Find my bottle.”
4. Glasses/AI indicate the bottle’s direction and selected target.
5. User says: “Bring it to the tray.”
6. Confirm motion, retrieve the lightweight bottle, and place it in the tray.
7. Show obstacle-alert feedback separately and report measured grasp reliability.

## Immediate next actions

- Read exact Jetson and Waveshare model labels and document power specs.
- Boot Jetson, check camera and inference dependencies.
- Verify arm control using its supported interface, initially with no load.
- Pick a fixed tabletop layout and two lightweight objects.
- Agree on one object-state JSON format and an arm-command API before independent implementation.
- Record milestone gates and a repeatable demonstration video.
