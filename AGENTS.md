# Optis agent instructions

Read `OPTIS_CONTEXT.md` and the authoritative repository docs before making changes:
- `docs/OPTIS_Build_Plan.md`
- `docs/OPTIS_Interfaces.md`
- `docs/OPTIS_Bench_and_Demo.md`

## Working principles
- This is a 36-hour HackUMass prototype. Prioritize a reproducible mock end-to-end workflow, then qualified bench integration.
- Follow the **v1 contracts in docs/OPTIS_Interfaces.md exactly**. If a requested change conflicts, flag it and seek team agreement rather than silently changing fields or behavior.
- Keep the first implementation local, offline-capable, and standard-library Python where practical. Do not require FastAPI, cloud calls, GPU, Jetson, or ESP32 for the mock path.
- Preserve ownership boundaries: perception under `src/optis/perception/`, arm under `src/optis/arm/`, interaction under `src/optis/interaction/`, integration in `src/optis/coordinator.py`.
- Frontend development is led by the user in Figma, reusing an existing home screen. Expose a minimal optional local UI bridge only after the internal contracts work; do not couple state-machine logic to UI.
- Start disabled. Mock/replay must never drive physical arm hardware. All real motion requires qualified bench mode, matching fixture and model, fresh validated table observations, separate local spotter approval, and verified safety preflight. Voice or model output never enables, approves, resets, jogs, or sends raw servo commands.
- Use short feature branches. Do not overwrite teammates' work or merge without review. Never commit secrets, local fixture calibration, identifiable recordings, or raw camera footage.
- Do not invent calibrated pose coordinates, serial settings, hardware model numbers, or successful bench results. A physical emergency power cutoff is outside software.

## Before editing
1. Inspect current repository state and latest docs.
2. State files and interfaces that will change.
3. Add/update tests for approvals, stale frames, wrong fixture, ambiguity, stop, hardware faults, and mock-only isolation as relevant.
4. Run the available tests and describe any that cannot run.

## Initial software milestone
`find bottle → retrieve → awaiting_approval → local spotter approves → fake arm pose sequence → complete`; an expired or wrong approval must produce **zero arm moves**.
