import type { BackendStatus, Health, Intent, Preview } from "./contracts";

/** Presentation boundary. The integrating application supplies data and callbacks. */
export type Reply = {
  request_id?: string;
  status: string;
  text?: string;
  speech?: string;
  data?: unknown;
  transcript?: string;
  voice_error?: string;
};
export type Destination = { name: string; lat: number; lon: number };
export type SessionEvent = {
  id: string;
  title: string;
  text: string;
  status: string;
  time: string;
};
export type WorkspaceData = {
  available?: boolean;
  health?: Health | null;
  status?: BackendStatus | null;
  reply?: Reply | null;
  events?: SessionEvent[];
  busy?: boolean;
  error?: string;
  preview?: Preview | null;
  previewing?: boolean;
  cameraError?: string;
  voiceState?: "idle" | "starting" | "recording" | "sending";
  voiceMessage?: string;
  canRecord?: boolean;
  hasResponseAudio?: boolean;
  sharingLocation?: boolean;
  locationMessage?: string;
};
export type WorkspaceActions = {
  onIntent?: (title: string, fields: Omit<Intent, "request_id">) => Promise<Reply | null>;
  onPreviewChange?: (enabled: boolean) => void;
  onStartVoice?: () => void;
  onStopVoice?: () => void;
  onCancelVoice?: () => void;
  onStopAudio?: () => void;
  onPlayResponse?: () => void;
  onStartLocation?: () => void;
  onStopLocation?: () => void;
  onClearSession?: () => void;
  onDismissError?: () => void;
  onLeave?: () => void;
  onPreferencesChange?: (preferences: {
    text: "standard" | "large";
    contrast: boolean;
    motion: boolean;
    announcements: boolean;
    playback: boolean;
    labels: boolean;
  }) => void;
};
export type WorkspaceProps = {
  exit: () => void;
  active: boolean;
  data?: WorkspaceData;
  actions?: WorkspaceActions;
};

export function destinationMatches(reply: Reply): Destination[] {
  if (reply.status !== "destinations" || !Array.isArray(reply.data)) return [];
  return reply.data
    .filter(
      (value): value is Destination =>
        !!value &&
        typeof value === "object" &&
        typeof value.name === "string" &&
        Number.isFinite(value.lat) &&
        Math.abs(value.lat) <= 85 &&
        Number.isFinite(value.lon) &&
        Math.abs(value.lon) <= 180,
    )
    .slice(0, 6);
}
