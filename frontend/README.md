# Optis Frontend

React 19, TypeScript, Vite, and Tailwind CSS frontend for the local Optis demo.

## Run with the backend

From the repository root, start the backend as described in the [main README](../README.md). In another terminal:

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm exec tsc --noEmit
pnpm dev
```

Vite proxies `/v1/*` to `http://127.0.0.1:8000`. Open the Vite URL, select **Explore OPTIS**, and enter the backend's `OPTIS_TOKEN`. The token stays in React memory and is cleared when leaving or refreshing. The workspace fetches health and status, runs authenticated intents, and can show camera preview and record a voice question when those services are configured. Route lookup needs a configured local Valhalla instance and a fresh usable phone or browser location fix.

For a build served by the backend, run `pnpm build`, set `OPTIS_FRONTEND=frontend/dist` when starting Optis, and open the backend root URL. The existing `/camera` page remains available for bench checks and replay. On iPhone Safari, use HTTPS for browser location; the tab must remain in the foreground. See the [iPhone sender](../clients/location-ios/README.md) for a separate GPS source.

The backend reports `arm: disabled`; the workspace does not provide arm approval or physical motion controls. Camera readiness and route availability are shown from live backend responses, not inferred from a healthy server.

## Checks

Run `pnpm exec tsc --noEmit` and `pnpm build` in this directory, plus `uv run python -m unittest discover -s tests -v` at the repository root. Browser checks should include the landing transition, reduced motion, small screens, token errors, camera unavailable state, microphone permission denial, and GPS permission denial.
