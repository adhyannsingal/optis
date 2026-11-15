# iPhone location sender

Create a SwiftUI iOS app target in Xcode, replace its generated app and view with the two Swift files here, and select your signing team. Set these target Info entries:

- `NSLocationWhenInUseUsageDescription` — Optis uses your position to test a checked outdoor route.
- `NSLocalNetworkUsageDescription` — Optis sends live location fixes to your local Optis backend.
- `NSAppTransportSecurity` → `NSAllowsLocalNetworking` — Yes for the private LAN development setup. Prefer HTTPS when sending location outside that setup.

Run the backend on the Mac or Jetson with `--host 0.0.0.0` on a private test network. On the phone, use the host's reachable local URL ending in `/v1/location`, enter the backend's `OPTIS_TOKEN`, and tap Start. Allow Local Network access and Precise Location while using the app. Keep the app in the foreground. With Valhalla configured, start sending fixes and select a walking destination in the dashboard. For the saved-route-only setup, start the checked route through `POST /v1/intent` before sending fixes.

Restart or replan the active route if the app restarts and begins its fix sequence at zero. After a disconnect, verify route status goes to weak signal before using the next cue. First field test uses one short verified outdoor segment with a sighted spotter.
