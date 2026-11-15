# Optis Frontend

React 19 + TypeScript + Vite + Tailwind CSS v4 frontend for Optis.

## Local development

```sh
cd frontend
pnpm install
pnpm dev
```

(Or `npm install && npm run dev`.)

## Connect to the Optis backend

Build with `pnpm build`. Start Optis with `OPTIS_FRONTEND=frontend/dist` and open the backend’s root URL. The **Explore Optis** button opens the app for voice questions, automatic item recall, and walking routes. Enter the backend’s `OPTIS_TOKEN` when prompted. See the [iPhone setup](../clients/location-ios/README.md) to supply live GPS fixes.

The backend’s `/camera` page is for bench checks and route replay.
