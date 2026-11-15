import type { BackendStatus, Health, Intent, Preview } from "./phase2/contracts";
import type { Reply } from "./phase2/workspaceTypes";

export class OptisApiError extends Error {
  constructor(message: string, readonly statusCode?: number) {
    super(message);
    this.name = "OptisApiError";
  }
}

async function request<T>(path: string, token?: string, init: RequestInit = {}, timeoutMs = 5000): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`/v1/${path}`, {
      ...init,
      signal: controller.signal,
      cache: "no-store",
      headers: {
        ...(init.body && !(init.body instanceof Blob) ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init.headers,
      },
    });
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null);
      const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
      throw new OptisApiError(typeof detail === "string" ? detail : `Optis request failed (HTTP ${response.status}).`, response.status);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof OptisApiError) throw error;
    throw new OptisApiError(controller.signal.aborted ? "Optis request timed out." : "Optis backend is unreachable.");
  } finally {
    window.clearTimeout(timeout);
  }
}

export const optisApi = {
  health: () => request<Health>("health"),
  status: (token: string) => request<BackendStatus>("status", token),
  preview: (token: string) => request<Preview>("camera/preview", token),
  navigationAudio: (token: string) => request<{ cue: { audio: string; audio_type: string; generation: number } | null }>("navigation/audio", token),
  intent: (token: string, fields: Omit<Intent, "request_id">) =>
    request<Reply>("intent", token, {
      method: "POST",
      body: JSON.stringify({ request_id: crypto.randomUUID(), ...fields }),
    }, 15000),
  voice: (token: string, audio: Blob) =>
    request<Reply & { audio?: string; audio_type?: string }>("voice", token, {
      method: "POST",
      body: audio,
      headers: { "Content-Type": audio.type },
    }, 30000),
};
