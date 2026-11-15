/** Backend contract types used by presentation components. */
export type Item = "keys" | "phone" | "bottle";
export type IntentKind =
  | "scene"
  | "find"
  | "remember"
  | "forget"
  | "start_route"
  | "next"
  | "pause"
  | "resume"
  | "stop"
  | "retrieve"
  | "find_destination"
  | "walk_to"
  | "navigate_to"
  | "choose_destination"
  | "recalculate";
export type Intent = {
  request_id: string;
  kind: IntentKind;
  item?: Item;
  place?: string;
  route_id?: string;
  query?: string;
  destination?: { name: string; lat: number; lon: number };
  choice?: number;
};
export type Health = {
  status: "ok";
  camera: string;
  live_route_configured: boolean;
  live_route_id: string | null;
  pedestrian_routing_configured: boolean;
  voice_configured: boolean;
  arm: "disabled";
};
export type Detection = {
  label: string;
  confidence: number;
  bbox_xyxy_px: [number, number, number, number];
  stable: boolean;
  position: "left" | "center" | "right";
};
export type Preview = {
  state: string;
  image: string | null;
  observation: {
    mode: string;
    source: string;
    frame_id: number;
    seen_ms: number;
    size_px: [number, number];
    detections: Detection[];
  } | null;
};
export type RouteMap = {
  active: boolean;
  paused: boolean;
  name: string;
  step: number;
  position: [number, number] | null;
  destination: [number, number];
  paths: [number, number][][];
  maneuvers: { index: number; instruction: string; end: [number, number] }[];
};
export type BackendStatus = {
  route: {
    status: string;
    text?: string;
    data?: { simulated?: boolean; active?: boolean; paused?: boolean; step?: number };
  } | null;
  route_map: RouteMap | null;
  location: {
    seq: number;
    horizontal_accuracy_m: number;
    age_seconds: number;
    ready: boolean;
    usable: boolean;
  } | null;
  audio: { generation: number; audio_error?: string | null };
  arm: "disabled";
};
export const items: Item[] = ["keys", "phone", "bottle"];
export function parseCommand(value: string): Omit<Intent, "request_id"> | null {
  const destination = /^(?:take me to|walk to|navigate to|start (?:the )?route to)\s+(.+)$/i.exec(
    value.trim(),
  );
  if (destination) {
    const query = destination[1]
      .replace(/[.?!]+$/, "")
      .replace(/\s+from\s+.+$/i, "")
      .trim()
      .slice(0, 200);
    if (query) return { kind: "navigate_to", query };
  }
  const text = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9 ]/g, "");
  if (["whats ahead", "what is ahead", "what do you see", "describe the scene"].includes(text))
    return { kind: "scene" };
  const object = /^(?:find (?:my )?|where are my |where is my )(keys|phone|bottle)$/.exec(text);
  if (object) return { kind: "find", item: object[1] as Item };
  const actions: Record<string, Omit<Intent, "request_id">> = {
    "start route replay": { kind: "start_route", route_id: "standard" },
    "next replay step": { kind: "next" },
    "pause route": { kind: "pause" },
    "resume route": { kind: "resume" },
    "stop route": { kind: "stop" },
    "stop navigation": { kind: "stop" },
    "recalculate route": { kind: "recalculate" },
    recalculate: { kind: "recalculate" },
  };
  if (actions[text]) return actions[text];
  const choice =
    /^(?:choose|select|the)\s+(first|second|third|fourth|fifth|sixth|[1-6])(?:\s+(?:one|destination|result))?$/.exec(
      text,
    );
  if (choice) {
    const word = choice[1];
    return {
      kind: "choose_destination",
      choice: /^\d$/.test(word)
        ? Number(word)
        : ["first", "second", "third", "fourth", "fifth", "sixth"].indexOf(word) + 1,
    };
  }
  return null;
}

/** Scoped phone token (when configured) authorizes the announcement endpoint. */
export type VisionAnnouncement = {
  camera_state: string;
  announcement: { event_id: string; text: string; expires_in_ms: number } | null;
};
