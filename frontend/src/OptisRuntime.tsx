import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { optisApi, OptisApiError } from "./optisApi";
import { useBrowserLocation } from "./useBrowserLocation";
import { Workspace } from "./phase2/Workspace";
import type { BackendStatus, Health, Intent, Preview } from "./phase2/contracts";
import type { Reply, SessionEvent, WorkspaceData } from "./phase2/workspaceTypes";

type VoiceState = NonNullable<WorkspaceData["voiceState"]>;
type VoiceReply = Reply & { audio?: string; audio_type?: string };

function message(error: unknown) {
  return error instanceof Error ? error.message : "Optis is unavailable.";
}

export default function OptisRuntime({ active, exit }: { active: boolean; exit: () => void }) {
  const [typedToken, setTypedToken] = useState("");
  const [token, setToken] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
  const [status, setStatus] = useState<BackendStatus | null>(null);
  const [available, setAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reply, setReply] = useState<Reply | null>(null);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [cameraError, setCameraError] = useState("");
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [voiceMessage, setVoiceMessage] = useState("");
  const [audioSource, setAudioSource] = useState("");
  const [playback, setPlayback] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const recordingTimer = useRef<number | null>(null);
  const player = useRef<HTMLAudioElement | null>(null);
  const routePlayer = useRef<HTMLAudioElement | null>(null);
  const generation = useRef(0);
  const mounted = useRef(true);
  const location = useBrowserLocation(token);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      generation.current += 1;
      if (recordingTimer.current !== null) window.clearTimeout(recordingTimer.current);
      if (recorder.current?.state === "recording") recorder.current.stop();
      stream.current?.getTracks().forEach((track) => track.stop());
      player.current?.pause();
      routePlayer.current?.pause();
    };
  }, []);

  useEffect(() => {
    if (!active || !token) return;
    let cancelled = false;
    let polling = false;
    const refresh = async () => {
      if (polling) return;
      polling = true;
      try {
        const [nextHealth, nextStatus] = await Promise.all([optisApi.health(), optisApi.status(token)]);
        if (cancelled) return;
        setHealth(nextHealth);
        setStatus(nextStatus);
        setAvailable(true);
        setError("");
      } catch (failure) {
        if (cancelled) return;
        setAvailable(false);
        setHealth(null);
        setStatus(null);
        if (failure instanceof OptisApiError && failure.statusCode === 401) {
          setToken("");
          setError("Session expired. Enter the current local token.");
        } else setError(message(failure));
      } finally {
        polling = false;
      }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), 1500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [active, token]);

  useEffect(() => {
    if (!active || !token || !previewing) return;
    let cancelled = false;
    let polling = false;
    const refresh = async () => {
      if (polling) return;
      polling = true;
      try {
        const frame = await optisApi.preview(token);
        if (!cancelled) {
          setPreview(frame);
          setCameraError("");
        }
      } catch (failure) {
        if (!cancelled) {
          setPreview(null);
          setCameraError(message(failure));
        }
      } finally {
        polling = false;
      }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), 500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [active, token, previewing]);

  useEffect(() => {
    if (!active || !token || !playback) return;
    let cancelled = false;
    let polling = false;
    const take = async () => {
      if (polling) return;
      polling = true;
      try {
        const { cue } = await optisApi.navigationAudio(token);
        if (cancelled || !cue?.audio || !cue.audio_type || !routePlayer.current) return;
        routePlayer.current.pause();
        routePlayer.current.src = `data:${cue.audio_type};base64,${cue.audio}`;
        await routePlayer.current.play();
      } catch (failure) {
        if (!cancelled) setVoiceMessage(`Navigation audio unavailable: ${message(failure)}`);
      } finally {
        polling = false;
      }
    };
    void take();
    const interval = window.setInterval(() => void take(), 1000);
    return () => { cancelled = true; window.clearInterval(interval); routePlayer.current?.pause(); };
  }, [active, token, playback]);

  const stopAudio = useCallback(() => {
    player.current?.pause();
    if (player.current) player.current.currentTime = 0;
    routePlayer.current?.pause();
    if (routePlayer.current) routePlayer.current.currentTime = 0;
  }, []);

  const cancelVoice = useCallback(() => {
    generation.current += 1;
    if (recordingTimer.current !== null) window.clearTimeout(recordingTimer.current);
    if (recorder.current?.state === "recording") recorder.current.stop();
    stream.current?.getTracks().forEach((track) => track.stop());
    recorder.current = null;
    stream.current = null;
    setVoiceState("idle");
  }, []);

  const clearSession = useCallback(() => {
    cancelVoice();
    stopAudio();
    location.stop();
    setToken("");
    setTypedToken("");
    setAvailable(false);
    setHealth(null);
    setStatus(null);
    setReply(null);
    setEvents([]);
    setPreviewing(false);
    setPreview(null);
    setAudioSource("");
  }, [cancelVoice, stopAudio, location]);

  async function connect(event: FormEvent) {
    event.preventDefault();
    const value = typedToken.trim();
    if (!value) return;
    setBusy(true);
    try {
      const [nextHealth, nextStatus] = await Promise.all([optisApi.health(), optisApi.status(value)]);
      setHealth(nextHealth);
      setStatus(nextStatus);
      setToken(value);
      setTypedToken("");
      setAvailable(true);
      setError("");
    } catch (failure) {
      setError(message(failure));
    } finally {
      setBusy(false);
    }
  }

  function showReply(title: string, response: Reply) {
    setReply(response);
    setEvents((previous) => [{
      id: crypto.randomUUID(), title,
      text: response.text ?? response.speech ?? response.status,
      status: response.status,
      time: new Date().toLocaleTimeString(),
    }, ...previous].slice(0, 30));
    if (response.voice_error) setVoiceMessage(response.voice_error);
  }

  async function runIntent(title: string, fields: Omit<Intent, "request_id">): Promise<Reply | null> {
    if (!token) return null;
    if (fields.kind === "stop") {
      cancelVoice();
      stopAudio();
      location.stop();
    }
    const version = ++generation.current;
    setBusy(true);
    setError("");
    try {
      const result = await optisApi.intent(token, fields);
      if (!mounted.current || version !== generation.current) return null;
      showReply(title, result);
      void optisApi.status(token).then(setStatus).catch(() => {});
      return result;
    } catch (failure) {
      if (mounted.current && version === generation.current) setError(message(failure));
      return null;
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  function startVoice() {
    if (!token || !health?.voice_configured || voiceState !== "idle") return;
    const format = ["audio/webm", "audio/mp4", "audio/wav"].find(
      (value) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(value),
    );
    if (!format || !navigator.mediaDevices?.getUserMedia) {
      setVoiceMessage("This browser cannot record a supported audio format.");
      return;
    }
    const version = ++generation.current;
    setVoiceState("starting");
    setVoiceMessage("");
    setAudioSource("");
    void navigator.mediaDevices.getUserMedia({ audio: true }).then((media) => {
      if (!mounted.current || version !== generation.current) {
        media.getTracks().forEach((track) => track.stop());
        return;
      }
      stream.current = media;
      const current = new MediaRecorder(media, { mimeType: format });
      recorder.current = current;
      const chunks: Blob[] = [];
      current.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      current.onerror = () => {
        cancelVoice();
        setVoiceMessage("Microphone recording failed.");
      };
      current.onstop = () => {
        if (recordingTimer.current !== null) window.clearTimeout(recordingTimer.current);
        media.getTracks().forEach((track) => track.stop());
        stream.current = null;
        recorder.current = null;
        if (!mounted.current || version !== generation.current) return;
        const audio = new Blob(chunks, { type: format });
        if (!audio.size) {
          setVoiceState("idle");
          setVoiceMessage("No audio was recorded.");
          return;
        }
        setVoiceState("sending");
        void optisApi.voice(token, audio).then((response: VoiceReply) => {
          if (!mounted.current || version !== generation.current) return;
          showReply("Voice question", response);
          setVoiceMessage(response.transcript ? `Heard: ${response.transcript}` : "Voice response received.");
          if (response.audio && response.audio_type) setAudioSource(`data:${response.audio_type};base64,${response.audio}`);
        }).catch((failure) => {
          if (mounted.current && version === generation.current) setVoiceMessage(message(failure));
        }).finally(() => {
          if (mounted.current && version === generation.current) setVoiceState("idle");
        });
      };
      current.start();
      setVoiceState("recording");
      recordingTimer.current = window.setTimeout(() => {
        if (current.state === "recording") current.stop();
      }, 6000);
    }).catch((failure) => {
      if (mounted.current && version === generation.current) {
        setVoiceState("idle");
        setVoiceMessage(message(failure));
      }
    });
  }

  const data: WorkspaceData = {
    available, health, status, reply, events, busy, error, preview, previewing, cameraError,
    voiceState, voiceMessage,
    canRecord: !!health?.voice_configured && typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia,
    hasResponseAudio: !!audioSource,
    sharingLocation: location.sharing,
    locationMessage: location.locationMessage,
  };

  return (
    <>
      {token ? (
        <Workspace active={active} exit={exit} data={data} actions={{
          onIntent: runIntent,
          onPreviewChange: (enabled) => { setPreviewing(enabled); if (!enabled) setPreview(null); },
          onStartVoice: startVoice,
          onStopVoice: () => { if (recorder.current?.state === "recording") recorder.current.stop(); },
          onCancelVoice: cancelVoice,
          onPlayResponse: () => { if (player.current) void player.current.play().catch(() => setVoiceMessage("Audio playback was blocked.")); },
          onStopAudio: stopAudio,
          onStartLocation: location.start,
          onStopLocation: location.stop,
          onClearSession: () => { setEvents([]); setReply(null); },
          onDismissError: () => setError(""),
          onLeave: clearSession,
          onPreferencesChange: (preferences) => setPlayback(preferences.playback),
        }} />
      ) : (
        <main className="optis-connect">
          <div className="optis-connect-card">
            <p className="optis-connect-brand">OPTIS</p>
            <h1>Connect to your local Optis session</h1>
            <p>Enter the token from the running Optis backend. It stays in this page until you leave or refresh.</p>
            <form onSubmit={(event) => void connect(event)}>
              <label htmlFor="optis-token">Local access token</label>
              <input id="optis-token" type="password" autoComplete="off" value={typedToken}
                onChange={(event) => setTypedToken(event.target.value)} required />
              <button type="submit" disabled={busy}>{busy ? "Connecting…" : "Connect"}</button>
            </form>
            {error && <p role="alert">{error}</p>}
            <button className="optis-connect-back" onClick={exit}>Return to landing</button>
          </div>
        </main>
      )}
      <audio ref={player} src={audioSource || undefined} hidden />
      <audio ref={routePlayer} hidden />
    </>
  );
}
