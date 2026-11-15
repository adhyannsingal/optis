import type { Preview, RouteMap } from "./contracts";
export function CameraFrame({
  frame,
  labels,
  selected,
}: {
  frame: Preview;
  labels: boolean;
  selected?: string;
}) {
  if (!frame.image || !frame.observation || frame.state !== "ready") return null;
  const [w, h] = frame.observation.size_px;
  if (!(w > 0 && h > 0)) return null;
  return (
    <div className="o-live-frame" style={{ aspectRatio: `${w}/${h}` }}>
      <img src={`data:image/jpeg;base64,${frame.image}`} alt="Current camera view" />
      <svg
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label="Object detections; descriptions are listed below"
      >
        {labels &&
          frame.observation.detections
            .filter((d) => d.stable && (!selected || selected === d.label))
            .map((d, i) => {
              const [x1, y1, x2, y2] = d.bbox_xyxy_px;
              return (
                <g key={i}>
                  <rect x={x1} y={y1} width={x2 - x1} height={y2 - y1} />
                  <text
                    x={Math.max(0, x1 + 4)}
                    y={Math.max(18, y1 - 7)}
                    fontSize={Math.max(14, w / 50)}
                  >
                    {d.label} {Math.round(d.confidence * 100)}%
                  </text>
                </g>
              );
            })}
      </svg>
    </div>
  );
}
export function RoutePreview({ route }: { route: RouteMap }) {
  const paths =
    route.paths?.filter(
      (p) =>
        Array.isArray(p) &&
        p.length > 0 &&
        p.every((v) => Array.isArray(v) && v.length === 2 && v.every(Number.isFinite)),
    ) ?? [];
  if (!paths.length)
    return <p>Route geometry is unavailable. Follow the current text instruction.</p>;
  const points = paths.flat();
  const lats = points.map((p) => p[0]),
    lons = points.map((p) => p[1]);
  const mid = (Math.min(...lats) + Math.max(...lats)) / 2;
  const scale = Math.cos((mid * Math.PI) / 180);
  const minX = Math.min(...lons) * scale,
    maxX = Math.max(...lons) * scale,
    minY = Math.min(...lats),
    maxY = Math.max(...lats);
  const span = Math.max((maxX - minX) / 520, (maxY - minY) / 320, 0.000001);
  const project = (p: [number, number]) => [
    300 + (p[1] * scale - (minX + maxX) / 2) / span,
    200 - (p[0] - (minY + maxY) / 2) / span,
  ];
  return (
    <>
      <svg
        className="o-route-svg"
        viewBox="0 0 600 400"
        role="img"
        aria-label={`North-up schematic route to ${route.name}`}
      >
        <text x="565" y="30">
          N ↑
        </text>
        {paths.map((p, i) => (
          <polyline key={i} points={p.map((v) => project(v).join(",")).join(" ")} />
        ))}
        {route.destination && (
          <circle
            cx={project(route.destination)[0]}
            cy={project(route.destination)[1]}
            r="9"
            className="o-destination"
          />
        )}
        {route.position && (
          <circle cx={project(route.position)[0]} cy={project(route.position)[1]} r="7" />
        )}
      </svg>
      <p>
        {route.name} · {route.paused ? "Paused" : route.active ? "Active" : "Finished"}
      </p>
      <p className="o-footnote">
        {route.maneuvers[route.step]?.instruction ?? "Route complete."} Schematic route line; no
        crossing or entrance detail.
      </p>
    </>
  );
}
