/** Typed PHAROS v1 HTTP adapter. Never persist a local operator token in browser storage. */
export type PharosHealth = {
  status: "ok";
  camera: string;
  live_route_configured: boolean;
  arm: "disabled";
};
export type PharosStatus = { route: unknown | null; arm: "disabled" };
export type PharosIntentKind =
  | "scene" | "find" | "remember" | "forget" | "start_route"
  | "next" | "pause" | "resume" | "stop" | "retrieve";
export type PharosIntent = {
  request_id: string;
  kind: PharosIntentKind;
  item?: "keys" | "bottle";
  place?: string;
  route_id?: string;
};
export type PharosIntentResult = {
  request_id: string;
  status: string;
  text?: string;
  data?: unknown;
};

export class PharosApiError extends Error {
  constructor(message: string, readonly statusCode?: number) {
    super(message);
    this.name = "PharosApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(`/v1/${path}`, {
      ...init,
      signal: controller.signal,
      cache: "no-store",
      headers: {
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    if (!response.ok) {
      const details: unknown = await response.json().catch(() => null);
      const message =
        typeof details === "object" && details !== null && "detail" in details &&
        typeof details.detail === "string"
          ? details.detail
          : `PHAROS request failed (HTTP ${response.status})`;
      throw new PharosApiError(message, response.status);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof PharosApiError) throw error;
    if (controller.signal.aborted) throw new PharosApiError("PHAROS backend timed out.");
    throw new PharosApiError("PHAROS backend is unreachable.");
  } finally {
    clearTimeout(timeout);
  }
}

export const pharosApi = {
  health: () => request<PharosHealth>("health"),
  status: (token: string) => request<PharosStatus>("status", {}, token),
  intent: (token: string, intent: PharosIntent) =>
    request<PharosIntentResult>("intent", { method: "POST", body: JSON.stringify(intent) }, token),
};
