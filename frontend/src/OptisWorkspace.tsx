import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useBrowserLocation } from "./useBrowserLocation";

type Destination = { name: string; lat: number; lon: number };
type Reply = { status: string; text: string; speech?: string; data?: unknown; transcript?: string;
  audio?: string; audio_type?: string; voice_error?: string };
type Health = { pedestrian_routing_configured: boolean; voice_configured: boolean };
type Status = { route: Reply | null; location: { usable: boolean; age_seconds: number;
  horizontal_accuracy_m: number } | null };

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Optis is unavailable.";
}

async function api<T>(path: string, token: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options, cache: "no-store",
    headers: { ...options.headers, Authorization: "Bearer " + token },
  });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Request failed.");
  return result as T;
}

function intent(token: string, kind: string, fields: Record<string, unknown> = {}) {
  const request_id = Array.from(crypto.getRandomValues(new Uint32Array(4))).join("-");
  return api<Reply>("/v1/intent", token, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id, kind, ...fields }),
  });
}

export default function OptisWorkspace({ exit }: { exit: () => void }) {
  const [typedToken, setTypedToken] = useState("");
  const [token, setToken] = useState("");
  const browserLocation = useBrowserLocation(token);
  const [health, setHealth] = useState<Health>();
  const [status, setStatus] = useState<Status>();
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [transcript, setTranscript] = useState("");
  const [places, setPlaces] = useState<Destination[]>([]);
  const [audio, setAudio] = useState("");
  const [speaking, setSpeaking] = useState(false);
  const [voiceState, setVoiceState] = useState<"idle" | "starting" | "recording" | "sending">("idle");
  const activeRecorder = useRef<MediaRecorder | null>(null);
  const recordingTimer = useRef<number | undefined>(undefined);
  const microphone = useRef<MediaStream | null>(null);
  const player = useRef<HTMLAudioElement>(null);
  const cueKey = useRef("");
  const requestVersion = useRef(0);
  const connected = useRef(false);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    const refresh = async () => {
      try {
        const current = await api<Status>("/v1/status", token, { signal: controller.signal });
        if (!controller.signal.aborted) setStatus(current);
      } catch (error) {
        if (!controller.signal.aborted) {
          setStatus(undefined);
          setMessage(errorMessage(error));
        }
      }
    };
    void refresh();
    const interval = window.setInterval(refresh, 900);
    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [token]);

  useEffect(() => {
    connected.current = true;
    return () => {
      connected.current = false;
      window.clearTimeout(recordingTimer.current);
      if (activeRecorder.current?.state === "recording") activeRecorder.current.stop();
      microphone.current?.getTracks().forEach(track => track.stop());
      window.speechSynthesis?.cancel();
    };
  }, []);

  useEffect(() => {
    const route = status?.route;
    if (!route) {
      cueKey.current = "";
      return;
    }
    const key = route.status + route.text;
    if (key === cueKey.current || voiceState !== "idle") return;
    cueKey.current = key;
    if (speaking && route.speech && window.speechSynthesis) {
      player.current?.pause();
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(route.speech));
    }
  }, [status?.route, speaking, voiceState]);

  async function connect(event: FormEvent) {
    event.preventDefault();
    const value = typedToken.trim();
    try {
      await api<Status>("/v1/status", value);
      setHealth(await api<Health>("/v1/health", value));
      setToken(value);
      setTypedToken("");
      setMessage("");
    } catch (error) {
      setMessage(errorMessage(error));
    }
  }

  function showReply(reply: Reply) {
    setMessage(reply.text + (reply.voice_error ? " " + reply.voice_error : ""));
    if (reply.status === "destinations") setPlaces(reply.data as Destination[]);
    if (reply.audio && reply.audio_type) setAudio(`data:${reply.audio_type};base64,${reply.audio}`);
  }

  async function submit(kind: string, fields: Record<string, unknown> = {}) {
    const version = ++requestVersion.current;
    setMessage("Working…");
    setTranscript("");
    setAudio("");
    if (kind === "find_destination") setPlaces([]);
    if (kind === "stop") window.speechSynthesis?.cancel();
    try {
      const reply = await intent(token, kind, fields);
      if (version !== requestVersion.current) return;
      showReply(reply);
      if (kind === "walk_to") setPlaces([]);
    } catch (error) {
      if (version === requestVersion.current) setMessage(errorMessage(error));
    }
  }

  async function record() {
    if (activeRecorder.current?.state === "recording") {
      activeRecorder.current.stop();
      return;
    }
    const format = ["audio/webm", "audio/mp4"].find(type => MediaRecorder.isTypeSupported(type));
    if (!format) {
      setMessage("This browser cannot record a supported audio format.");
      return;
    }
    const version = ++requestVersion.current;
    setVoiceState("starting");
    setAudio("");
    setTranscript("");
    setMessage("");
    window.speechSynthesis?.cancel();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!connected.current) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      microphone.current = stream;
      const recorder = new MediaRecorder(stream, { mimeType: format });
      activeRecorder.current = recorder;
      const chunks: Blob[] = [];
      recorder.ondataavailable = event => chunks.push(event.data);
      recorder.onerror = () => {
        ++requestVersion.current;
        setMessage("Microphone recording failed.");
        window.clearTimeout(recordingTimer.current);
        stream.getTracks().forEach(track => track.stop());
        setVoiceState("idle");
      };
      recorder.onstop = async () => {
        window.clearTimeout(recordingTimer.current);
        stream.getTracks().forEach(track => track.stop());
        microphone.current = null;
        activeRecorder.current = null;
        if (!connected.current) return;
        if (version !== requestVersion.current) {
          setVoiceState("idle");
          return;
        }
        setVoiceState("sending");
        try {
          const reply = await api<Reply>("/v1/voice", token, {
            method: "POST", headers: { "Content-Type": format },
            body: new Blob(chunks, { type: format }),
          });
          if (connected.current && version === requestVersion.current) {
            setTranscript(reply.transcript ?? "");
            setPlaces([]);
            showReply(reply);
          }
        } catch (error) {
          if (connected.current && version === requestVersion.current) setMessage(errorMessage(error));
        } finally {
          if (connected.current) setVoiceState("idle");
        }
      };
      recorder.start();
      setVoiceState("recording");
      recordingTimer.current = window.setTimeout(() => {
        if (recorder.state === "recording") recorder.stop();
      }, 6000);
    } catch (error) {
      microphone.current?.getTracks().forEach(track => track.stop());
      if (connected.current) {
        setVoiceState("idle");
        setMessage(errorMessage(error));
      }
    }
  }

  const gps = status?.location;
  const gpsText = !gps ? "Waiting for GPS" : gps.age_seconds > 5 ? "GPS signal lost"
    : gps.usable ? "GPS ready" : "GPS accuracy too low";
  const canRecord = Boolean(health?.voice_configured && typeof navigator.mediaDevices?.getUserMedia === "function" && typeof window.MediaRecorder === "function");
  const voiceLabel = { idle: "Ask Optis", starting: "Opening microphone…",
    recording: "Stop and ask", sending: "Transcribing…" }[voiceState];

  return (
    <main className="optis-app-shell optis-workspace">
      <div className="optis-workspace-header">
        <h1 className="app-shell-brand">OPTIS</h1>
        <button onClick={exit}>Return to landing</button>
      </div>
      {!token ? (
        <form onSubmit={connect}>
          <label>Optis access token
            <input type="password" value={typedToken} onChange={event => setTypedToken(event.target.value)} required />
          </label>
          <button>Connect</button>
        </form>
      ) : (
        <>
          <section aria-labelledby="voice-heading">
            <h2 id="voice-heading">Ask Optis</h2>
            <div className="optis-actions">
              <button onClick={record} disabled={!canRecord || voiceState === "sending" || voiceState === "starting"}>{voiceLabel}</button>
              <button onClick={() => submit("find", { item: "keys" })}>Find keys</button>
            </div>
            {!canRecord && <p>Voice is unavailable on this connection.</p>}
            {transcript && <p>Heard: {transcript}</p>}
            {audio && <audio ref={player} src={audio} controls autoPlay />}
          </section>
          <section aria-labelledby="walk-heading">
            <h2 id="walk-heading">Walk somewhere</h2>
            <p><span role="status">{gpsText}</span>{gps && gps.age_seconds <= 5 &&
              ` · ±${gps.horizontal_accuracy_m.toFixed(0)} m`}</p>
            <div className="optis-actions">
              <button onClick={browserLocation.sharing ? () => browserLocation.stop() : browserLocation.start}>
                {browserLocation.sharing ? "Stop sharing location" : "Use my location"}
              </button>
            </div>
            {browserLocation.locationMessage && <p role="status">{browserLocation.locationMessage}</p>}
            {health?.pedestrian_routing_configured && (
              <form onSubmit={event => { event.preventDefault(); void submit("find_destination", { query: query.trim() }); }}>
                <label>Destination
                  <input value={query} onChange={event => setQuery(event.target.value)} required maxLength={200} />
                </label>
                <button>Find destination</button>
              </form>
            )}
            {places.length > 0 && (
              <ul className="optis-destinations">
                {places.map(place => (
                  <li key={`${place.name}:${place.lat}:${place.lon}`}>
                    <button disabled={!gps?.usable || gps.age_seconds > 5} onClick={() => submit("walk_to", { destination: place })}>
                      {place.name}
                      {places.some(other => other !== place && other.name === place.name) &&
                        ` (${place.lat.toFixed(5)}, ${place.lon.toFixed(5)})`}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <p aria-live="polite">{status?.route?.text}</p>
            {status?.route && status.route.status !== "arrived" && (
              <button onClick={() => submit("stop")}>Stop route</button>
            )}
            {typeof window.speechSynthesis !== "undefined" && <label><input type="checkbox" checked={speaking} onChange={event => setSpeaking(event.target.checked)} /> Speak route cues</label>}
            {health?.pedestrian_routing_configured && <p>Map data © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a></p>}
          </section>
        </>
      )}
      <output aria-live="polite">{message}</output>
    </main>
  );
}
