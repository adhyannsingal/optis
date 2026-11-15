# OPTIS frontend handoff

Branch: `Frontend`. Frontend presentation only. Backend features checked against merged team source at `origin/main` commit `90fb25c`.

## Included

- Approved OPTIS landing, original glasses image and camera zoom; sky-blue landing and deep-blue destination.
- Home, Assistant, Vision, Navigate and Settings.
- Responsive sidebar/bottom navigation, global Voice & Audio, local accessibility preferences, empty/loading/error states and memory-deletion confirmation.
- All 80 YOLO categories plus optional keyring. Targeted lookup/memory remains keys, phone and bottle, matching the API.
- Components that render supplied camera frames/detection boxes, schematic routes, destination candidates, route state, GPS fixes, voice states and confirmed responses.
- Product copy without phase labels, commit references, Xcode setup text, preview notices or fabricated results.

## Teammate integration boundary

`src/phase2/Workspace.tsx` accepts `active`, `exit`, optional `data: WorkspaceData`, and optional `actions: WorkspaceActions`. Types are in `workspaceTypes.ts`.

```tsx
<Workspace active={page === 'app'} exit={exitApp}
  data={workspaceData} actions={workspaceActions} />
```

The current `App.tsx` intentionally supplies only `active` and `exit`. Missing runtime values render neutral empty states and disable service actions. Navigation, dialogs, filtering, examples and local accessibility preferences work independently.

No new API transport, token entry, microphone recording, camera capture, audio playback or location sharing is implemented. No backend files changed. The existing unused `pharosApi.ts` and Vite proxy are pre-existing branch code; the new Workspace does not use them.

| UI | Supplied data | Action callback / intent |
| --- | --- | --- |
| System status | health, status, available, busy, error | Supply actual `/v1/health` and `/v1/status` results |
| Assistant / scene / find | reply, events | `onIntent(title, fields)`: scene, find |
| Memory | per-item response | remember, find, forget (after confirmation) |
| Camera | preview, previewing, cameraError | onPreviewChange |
| Voice | voiceState, voiceMessage, canRecord, hasResponseAudio | onStartVoice, onStopVoice, onCancelVoice, onPlayResponse, onStopAudio |
| Destinations | confirmed destinations reply, max six | find_destination, navigate_to, choose_destination, walk_to |
| Routes | route and route_map | pause, resume, stop, recalculate |
| Demo / checked route | actual route flags and checked-route ID | start_route: standard/noisy/configured ID; next for replay only |
| GPS | latest location status, sharingLocation, locationMessage | onStartLocation, onStopLocation |
| Preferences | browser-local preferences | onPreferencesChange |
| Session / exit | events | onClearSession, onDismissError, onLeave |

The integrating host owns authentication, unique request IDs, requests, polling, runtime validation, media permissions, recording limits, audio generation, cancellation and cleanup. `onIntent` returns a confirmed Reply; the host supplies updated reply/events/status through data. Do not infer camera readiness from a healthy server. The chair-announcement endpoint is available to the team integration; it does not imply obstacle clearance.

## Files

- App.tsx: mounts the application destination while retaining the approved landing and animation.
- phase2/Workspace.tsx: pages and presentation controls.
- phase2/workspaceTypes.ts: data and callback boundary.
- phase2/LiveViews.tsx: camera and route rendering only.
- phase2/contracts.ts: backend payload types and bounded command parser.
- phase2/modelClasses.ts: model manifest categories.
- phase2/Icon.tsx and workspace.css: local icons and scoped styles.

## Validation

From frontend: `npx tsc --noEmit` and `npm run build`. Backend source review previously ran all 21 team unittest cases in an isolated archive. This handoff does not claim live service, hardware, microphone, phone GPS or screen-reader device certification.
