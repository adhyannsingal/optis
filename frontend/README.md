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


## Live GPS in Safari

Open the product app over HTTPS on the iPhone, connect with the Optis access token, and tap **Use my location** under **Walk somewhere**. Allow precise location when prompted. Wait for **GPS ready**, then choose a destination. Turn on **Speak route cues** if you want audible turns. Location sharing pauses when the tab is hidden. Keep the tab in the foreground while walking. The Mac’s localhost address is for local testing.
