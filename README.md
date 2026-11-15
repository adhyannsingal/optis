# Optis

Optis is an assistive prototype for route guidance, object finding, and voice-controlled tabletop retrieval.

## Run the backend locally

```sh
uv sync --locked --extra test --extra vision
export OPTIS_TOKEN="$(openssl rand -hex 24)"
uv run uvicorn optis.api:from_environment --factory --host 127.0.0.1 --port 8000
```

Open [the local demo](http://127.0.0.1:8000/camera), enter the Optis token and click **Start preview**. The bench page has live camera boxes, item queries, voice, route replay, and phone fix status. To run the product UI, build the [React frontend](frontend/README.md) and set `OPTIS_FRONTEND=frontend/dist` before launching the backend.

Keep the token in the running shell. `GET /v1/health` reports readiness. Interactive API docs are at `/docs`. Send the token as `Authorization: Bearer <token>` for status, intents and phone fixes. Use one server worker because route state and camera ownership are local to the process. To carry over saved item placements, set `OPTIS_DB` to your existing SQLite file when starting Optis.

## Demo inputs

- **Camera.** Set `OPTIS_MODEL=models/yolov8n.onnx`, `OPTIS_CAMERA` to the USB camera index, and optionally `OPTIS_CAMERA_NAME="Brio 100"`. Use `ffmpeg -f avfoundation -list_devices true -i ''` on macOS to find the index. On Linux use a UVC device path. The W11 adapter takes a private capture URL and requires its `X-OPTIS-Frame-Age-Us` header. Regenerate and reflash the W11 sketch if it was built before that header was introduced. If the ONNX file is missing, use `scripts/export_model.py` with Ultralytics, ONNX and ONNX Runtime. Keep the resulting checksum manifest with its matching model.
- **Keys and phone.** A local experimental YOLOE detector looks for a generic keyring, and YOLOv8 looks for a generic phone. To prepare a keyring checkpoint, install Ultralytics in the demo environment, run `python scripts/prepare_keyring_model.py`, and set `OPTIS_KEYRING_MODEL=models/keyring-yoloe-26s-seg.pt`. Use a local checkpoint you trust. Hold a single keyring or phone in view, ask for it, move it away, and ask again for its last-seen time. Optis saves stable sightings automatically and stores sighting metadata without photos.
- **Grok Voice.** In the Mac Terminal (zsh) that will run Optis, use `read -rs 'XAI_API_KEY?xAI API key: '; export XAI_API_KEY; echo` to load the key with typing hidden, then start the server. Click **Record question**, say “Where are my keys?” and click **Stop and ask**. The adapter sends audio to xAI speech-to-text, runs the local query, and sends its reply text to xAI text-to-speech. For an existing local demo configured with `OPTIS_XAI_KEY_FILE=$PWD/.xai-key`, run `zsh scripts/set_demo_voice.zsh` and restart the browser preview to enable recording.
- **Navigation.** Start **Route replay** or **Replay weak GPS** and click **Next replay step**. To try real phone fixes, use the [iPhone sender](clients/location-ios/README.md) on a private LAN. For route guidance, copy `config/route.example.json` to `config/route.local.json`, enter physically checked outdoor waypoints and one instruction per segment, then set `verified` and launch with `OPTIS_ROUTE=config/route.local.json`. Start the checked route in the demo. The GPS status shows fix receipt, age, and reported accuracy. Use a sighted spotter for the walking test.

Run `uv run python -m unittest discover -s tests -v` for the backend checks. This build keeps the arm disabled.


## Local walking routes with Valhalla

Use a regional OpenStreetMap extract. This example builds the Massachusetts walking network. Start Docker Desktop first and run these commands from the repository root:

```sh
mkdir -p .valhalla
curl -fL --output .valhalla/massachusetts.osm.pbf \
  https://download.geofabrik.de/north-america/us/massachusetts-latest.osm.pbf
docker run -d --name optis-valhalla -p 127.0.0.1:8002:8002 \
  -v "$PWD/.valhalla:/custom_files" \
  -e server_threads=4 -e build_admins=False -e build_time_zones=False \
  ghcr.io/valhalla/valhalla-scripted@sha256:5402c8543f083350dade401673cd66071f17e3220983aef4cd10296c72dee77d
uv run --no-project --with osmium python scripts/index_map_places.py \
  .valhalla/massachusetts.osm.pbf .valhalla/places.sqlite3
```

First startup builds the routing graph. Check `docker logs optis-valhalla` and wait for `curl http://127.0.0.1:8002/status` to respond. On macOS, allow Docker to read the workspace if prompted. To use the same graph on later runs, run `docker start optis-valhalla`.

Start Optis with `OPTIS_VALHALLA_URL=http://127.0.0.1:8002` and `OPTIS_PLACES_INDEX=.valhalla/places.sqlite3`. Use a private LAN and a randomly generated Optis token when connecting the iPhone sender. Keep the Valhalla port on loopback.

In the dashboard, enter a place name, mapped address, or `latitude, longitude`. Select the destination from the results to calculate a pedestrian route from the latest usable iPhone fix. With voice enabled, “Take me to Du Bois Library” finds the destination choices. Turn on **Speak route cues** to hear guidance from the dashboard. A weak signal holds progress. To recalculate from a new position, select the destination again after a fresh fix. Test walking cues with a sighted spotter. A map route describes the path and turns. Obstacle and crossing clearance require separate sensing and checks.

Both destination lookup and route calculation run locally after setup. Results depend on the coverage and contents of the installed map. The place index searches mapped names and numbered addresses. Coordinates can be used for any destination in routing coverage.
