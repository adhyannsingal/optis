# PHAROS Frontend

React 19 + TypeScript + Vite 8 + Tailwind CSS v4.

## Local development

Start the PHAROS Python backend with a local `PHAROS_TOKEN` and run it on
`127.0.0.1:8000`. In a second terminal:

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm exec tsc --noEmit
pnpm run build
pnpm dev
```

Vite proxies `/v1/*` to `http://127.0.0.1:8000` during development. Open
the Vite URL, enter the same local token in the dark application screen, and
try the scene/find/demo route commands. A local backend that is not running
will display **offline**; a camera-disabled server reports its actual camera
status rather than pretending live vision works.

The token is held **only in React component memory**, not localStorage,
cookies, URL parameters, or build-time `VITE_*` variables. Refreshing or
leaving the app clears it. Do not deploy a public website that accepts this
operator token. For any deployment use an authenticated HTTPS reverse proxy
and server-side authorization rather than exposing the local device token.

The `retrieve` backend intent currently returns `arm_disabled`; the UI
does not issue retrieval or approval commands. Hardware integration is
supervised and must follow the project safety/bench spec.

## Validation

`pnpm exec tsc --noEmit` and `pnpm run build` run in GitHub Actions for
frontend branches. Browser testing is still required for: slow/missing PNG,
CTA/wheel/touch/keyboard, animation handoff, reduced motion, and responsive
viewport sizes. A passing build is not proof of bug-free animation.
