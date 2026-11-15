# OPTIS

PHAROS is an assistive prototype for route guidance, object finding, and voice-controlled tabletop retrieval.

## Run the backend locally

```sh
uv sync --locked --extra test --extra vision
export PHAROS_TOKEN="$(openssl rand -hex 24)"
uv run uvicorn pharos.api:from_environment --factory --host 127.0.0.1 --port 8000
```

Keep the token in the running shell. `GET /v1/health` reports readiness. Interactive API docs are at `/docs`. Send the token as `Authorization: Bearer <token>` for status, intents and phone fixes. Use one server worker because route state and camera ownership are local to the process.

- Send `{"request_id":"find-1","kind":"find","item":"bottle"}` to `POST /v1/intent`. Use `kind=remember` and a `place` to set a confirmed placement.
- Send `kind=start_route` with `route_id=standard` or `noisy`, then send `kind=next` to advance replay.
- For vision, provide a matching YOLOv8n ONNX file and checksum manifest. Set `PHAROS_MODEL` to the ONNX path, `PHAROS_MODEL_MANIFEST` if using another manifest, and `PHAROS_CAMERA` to a camera index, a Linux UVC device path, or the W11 private capture URL. Use `scripts/export_model.py` from an environment with Ultralytics, ONNX and ONNX Runtime to export the checksum-pinned checkpoint. The generated manifest must match that export. A W11 frame needs the `X-PHAROS-Frame-Age-Us` header for live guidance.
- For live GPS, use the [iPhone sender](clients/location-ios/README.md). Copy `config/route.example.json` to `config/route.local.json`, enter measured outdoor waypoints as latitude/longitude pairs and one instruction per segment, set `verified` after walking the route, and start with `PHAROS_ROUTE=config/route.local.json`. The backend rejects weak or stale fixes. Use the route ID in your file to start live guidance.
- Run `uv run python -m unittest discover -s tests -v` for the backend checks. The arm remains disabled in this implementation.
