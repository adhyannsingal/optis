import { canCancelRecording } from "../sessionLifecycle";
import { destinationMatches, type Destination, type WorkspaceProps } from "./workspaceTypes";
import { CameraFrame, RoutePreview } from "./LiveViews";
import { modelClasses } from "./modelClasses";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import { items, parseCommand, type Intent, type Item } from "./contracts";
import "./workspace.css";

type Page = "Home" | "Assistant" | "Vision" | "Navigate" | "Settings";

type Preferences = {
  text: "standard" | "large";
  contrast: boolean;
  motion: boolean;
  announcements: boolean;
  playback: boolean;
  labels: boolean;
};
const defaults: Preferences = {
  text: "standard",
  contrast: false,
  motion: false,
  announcements: true,
  playback: false,
  labels: true,
};
const pages: { name: Page; icon: IconName; title: string; subtitle: string }[] = [
  {
    name: "Home",
    icon: "home",
    title: "OPTIS Overview",
    subtitle: "Awareness, guidance, and the things that matter.",
  },
  {
    name: "Assistant",
    icon: "assistant",
    title: "OPTIS Assistant",
    subtitle: "Ask for a scene description, locate an object, or control navigation.",
  },
  {
    name: "Vision",
    icon: "vision",
    title: "OPTIS Vision",
    subtitle: "Understand what the camera can currently detect.",
  },
  {
    name: "Navigate",
    icon: "navigate",
    title: "Walking Navigation",
    subtitle: "Route guidance using available mapped paths and phone location.",
  },
  {
    name: "Settings",
    icon: "settings",
    title: "OPTIS Settings",
    subtitle: "Control your experience and understand system availability.",
  },
];
function Panel({
  title,
  children,
  className = "",
  aside,
}: {
  title: string;
  children: ReactNode;
  className?: string;
  aside?: ReactNode;
}) {
  return (
    <section className={`o-panel ${className}`}>
      <div className="o-panel-heading">
        <h2>{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}
function Empty({
  icon = "scene",
  title,
  children,
}: {
  icon?: IconName;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="o-empty">
      <span className="o-empty-icon">
        <Icon name={icon} size={28} />
      </span>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function Button({
  children,
  onClick,
  disabled = false,
  primary = false,
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  primary?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      className={`o-button ${primary ? "o-primary" : ""}`}
      onClick={onClick}
      disabled={disabled}
      title={title ?? (disabled ? "This action is not available right now." : undefined)}
    >
      {children}
    </button>
  );
}
function Toggle({
  label,
  detail,
  checked,
  change,
}: {
  label: string;
  detail?: string;
  checked: boolean;
  change: () => void;
}) {
  return (
    <label className="o-toggle-row">
      <span>
        <strong>{label}</strong>
        {detail && <small>{detail}</small>}
      </span>
      <input type="checkbox" checked={checked} onChange={change} />
    </label>
  );
}
function OpticsArt() {
  return (
    <svg className="o-optics" viewBox="0 0 400 300" fill="none" aria-hidden="true">
      <g stroke="currentColor">
        <ellipse cx="240" cy="150" rx="112" ry="112" />
        <ellipse cx="240" cy="150" rx="84" ry="84" />
        <ellipse cx="240" cy="150" rx="54" ry="54" />
        <ellipse cx="240" cy="150" rx="24" ry="24" />
        <path d="M0 150h400M240 0v300M40 30l200 120L40 270M70 80l170 70L70 220" />
        <path d="m310 65 30-30m-30 200 30 30" />
      </g>
      <circle cx="240" cy="150" r="7" fill="currentColor" />
    </svg>
  );
}
export function Workspace({ exit, active, data, actions }: WorkspaceProps) {
  const [page, setPage] = useState<Page>("Home");
  const [visionTab, setVisionTab] = useState("Live Camera");
  const [item, setItem] = useState<Item>("phone");
  const [requestText, setRequestText] = useState("");
  const [place, setPlace] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("");
  const [objectClass, setObjectClass] = useState("cell phone");
  const [audioOpen, setAudioOpen] = useState(false);
  const [forgetItem, setForgetItem] = useState<Item | null>(null);
  const [validation, setValidation] = useState("");
  const [matches, setMatches] = useState<Destination[]>([]);
  const [expires, setExpires] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [preferences, setPreferences] = useState<Preferences>(() => {
    try {
      const p = JSON.parse(localStorage.getItem("optis-ui-preferences") ?? "{}");
      return {
        text: p?.text === "large" ? "large" : "standard",
        contrast: p?.contrast === true,
        motion: p?.motion === true,
        announcements: p?.announcements !== false,
        playback: p?.playback === true,
        labels: p?.labels !== false,
      };
    } catch {
      return defaults;
    }
  });
  const live = {
    health: data?.health ?? null,
    status: data?.status ?? null,
    reply: data?.reply ?? null,
    events: data?.events ?? [],
    busy: data?.busy ?? false,
    error: data?.error ?? "",
    preview: data?.preview ?? null,
    previewing: data?.previewing ?? false,
    cameraError: data?.cameraError ?? "",
    ready: data?.available === true,
    clearEvents: () => actions?.onClearSession?.(),
    setError: (_value: string) => actions?.onDismissError?.(),
    setPreviewing: (enabled: boolean) => actions?.onPreviewChange?.(enabled),
    run: (title: string, fields: Omit<Intent, "request_id">) =>
      actions?.onIntent?.(title, fields) ?? Promise.resolve(null),
  };
  const media = {
    voiceState: data?.voiceState ?? "idle",
    voiceMessage: data?.voiceMessage ?? "",
    canRecord: data?.canRecord === true,
    audioSource: data?.hasResponseAudio === true,
    sharing: data?.sharingLocation === true,
    locationMessage: data?.locationMessage ?? "",
    startVoice: () => actions?.onStartVoice?.(),
    stopVoice: () => actions?.onStopVoice?.(),
    cancelVoice: () => actions?.onCancelVoice?.(),
    stopAudio: () => actions?.onStopAudio?.(),
    playResponse: () => actions?.onPlayResponse?.(),
    startLocation: () => actions?.onStartLocation?.(),
    stopLocation: () => actions?.onStopLocation?.(),
  };
  const heading = useRef<HTMLHeadingElement>(null);
  const workspace = useRef<HTMLDivElement>(null);
  const audioDialog = useRef<HTMLDialogElement>(null);
  const forgetDialog = useRef<HTMLDialogElement>(null);
  const update = <K extends keyof Preferences>(key: K, value: Preferences[K]) =>
    setPreferences((p) => ({ ...p, [key]: value }));
  useEffect(() => {
    try {
      localStorage.setItem("optis-ui-preferences", JSON.stringify(preferences));
    } catch {
      /* Preferences remain usable without storage. */
    }
    actions?.onPreferencesChange?.(preferences);
  }, [preferences, actions?.onPreferencesChange]);
  useEffect(() => {
    if (audioOpen) audioDialog.current?.showModal();
    else audioDialog.current?.close();
  }, [audioOpen]);
  useEffect(() => {
    if (forgetItem) forgetDialog.current?.showModal();
    else forgetDialog.current?.close();
  }, [forgetItem]);
  useEffect(() => {
    if (!active) {
      setAudioOpen(false);
      setForgetItem(null);
      return;
    }
    const read = () => {
      const p = pages.find((p) => `#/app/${p.name.toLowerCase()}` === location.hash);
      if (p) setPage(p.name);
    };
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, [active]);
  useEffect(() => {
    if (active) {
      workspace.current?.scrollTo({ top: 0 });
      heading.current?.focus({ preventScroll: true });
    }
  }, [page, active]);
  useEffect(() => {
    if (live.reply?.status === "destinations") {
      setMatches(destinationMatches(live.reply));
      setExpires(Date.now() + 60000);
    } else if (live.reply && ["route_started", "stopped"].includes(live.reply.status)) {
      setMatches([]);
      setExpires(0);
    }
  }, [live.reply]);
  useEffect(() => {
    if (!expires) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [expires]);
  const go = (p: Page, tab?: string) => {
    setPage(p);
    if (tab) setVisionTab(tab);
    setValidation("");
    location.hash = `/app/${p.toLowerCase()}`;
  };
  const pageInfo = pages.find((p) => p.name === page)!;
  const route = live.status?.route;
  const routeActive = !!route?.data?.active;
  const paused = !!route?.data?.paused;
  const simulated = !!route?.data?.simulated;
  const gps = live.status?.location;
  const cameraReady = live.health?.camera === "ready";
  const voiceReady = live.ready && !!live.health?.voice_configured && !!actions?.onStartVoice;
  const recording = media.voiceState === "recording";
  const voiceBusy = media.voiceState !== "idle";
  const canAct = live.ready && !!actions?.onIntent && !live.busy && !voiceBusy;
  const act = async (title: string, fields: Omit<Intent, "request_id">) => {
    setValidation("");
    if (!canAct && fields.kind !== "stop") return null;
    if (fields.kind === "stop") {
      media.cancelVoice();
      media.stopAudio();
      media.stopLocation();
    } else media.stopAudio();
    try {
      return await live.run(title, fields);
    } catch {
      setValidation("The request could not be completed. Please try again.");
      return null;
    }
  };
  const submitCommand = () => {
    const parsed = parseCommand(requestText);
    if (!parsed) {
      setValidation(
        "Try a scene description, an item lookup, or a navigation command. Choose an example below.",
      );
      return;
    }
    void act(requestText.trim(), parsed);
    setRequestText("");
  };
  const lookupSupported = ["cell phone", "bottle", "keyring"].includes(objectClass);
  const setCategory = (category: string) => {
    setObjectClass(category);
    if (category === "cell phone") setItem("phone");
    if (category === "bottle") setItem("bottle");
    if (category === "keyring") setItem("keys");
  };
  const itemSelect = (
    <label className="o-field">
      Item
      <select value={item} onChange={(e) => setItem(e.target.value as Item)}>
        {items.map((i) => (
          <option key={i} value={i}>
            {i[0].toUpperCase() + i.slice(1)}
          </option>
        ))}
      </select>
    </label>
  );
  const routeButtons = (
    <div className="o-actions">
      <Button
        disabled={!canAct || !routeActive || paused}
        onClick={() => void act("Pause route", { kind: "pause" })}
      >
        Pause
      </Button>
      <Button
        disabled={!canAct || !routeActive || !paused}
        onClick={() => void act("Resume route", { kind: "resume" })}
      >
        Resume
      </Button>
      <Button
        disabled={!live.ready || (!routeActive && !live.busy && !voiceBusy)}
        onClick={() => void act("Stop navigation", { kind: "stop" })}
      >
        Stop
      </Button>
      <Button
        disabled={!canAct || !routeActive || !live.status?.route_map || !gps?.ready}
        onClick={() => void act("Recalculate route", { kind: "recalculate" })}
      >
        Recalculate Route
      </Button>
    </div>
  );
  const voiceControls = (
    <>
      <h3>Speak to OPTIS</h3>
      <p>Ask what’s ahead, find an item, or control navigation.</p>
      <div className="o-actions">
        <Button
          primary
          disabled={!voiceReady || !media.canRecord || voiceBusy || live.busy}
          onClick={() => void media.startVoice()}
        >
          <Icon name="mic" />
          {media.voiceState === "starting" ? "Opening microphone…" : "Start Speaking"}
        </Button>
        <Button disabled={!recording} onClick={media.stopVoice}>
          Stop &amp; Ask
        </Button>
        <Button disabled={!media.audioSource} onClick={media.playResponse}>
          Play Response
        </Button>
        {canCancelRecording(media.voiceState) && <Button onClick={media.cancelVoice}>Cancel Recording</Button>}
      </div>
      <p className="o-voice-status" role="status">
        {media.voiceMessage ||
          (recording
            ? "Listening…"
            : media.voiceState === "sending"
              ? "Processing your submitted command…"
              : "Choose a voice command or type a request in Assistant.")}
      </p>
      {live.reply?.transcript && (
        <p>
          <strong>Heard You Say: </strong>
          {live.reply.transcript}
        </p>
      )}
      <Toggle
        label="Play spoken route cues"
        detail="Play navigation audio supplied by OPTIS."
        checked={preferences.playback}
        change={() => update("playback", !preferences.playback)}
      />
      {live.status?.audio.audio_error && (
        <p role="status">Navigation audio unavailable: {live.status.audio.audio_error}</p>
      )}
    </>
  );
  const systemRows = [
    ["OPTIS", live.ready ? "Available" : "—"],
    [
      "Camera",
      live.ready
        ? live.health?.camera === "disabled"
          ? "Unavailable"
          : (live.health?.camera?.replace(/_/g, " ") ?? "—")
        : "—",
    ],
    ["Voice", live.ready ? (live.health?.voice_configured ? "Available" : "Unavailable") : "—"],
    [
      "GPS",
      gps
        ? gps.ready
          ? "Ready"
          : gps.age_seconds > 5
            ? "Location is stale"
            : "Accuracy too low"
        : "No location received",
    ],
    [
      "Routing",
      live.ready ? (live.health?.pedestrian_routing_configured ? "Available" : "Unavailable") : "—",
    ],
  ];
  const lastResult = (
    <>
      {live.reply ? (
        <div className="o-result">
          <span className="o-tag">{live.reply.status.replace(/_/g, " ")}</span>
          <p>{live.reply.text ?? live.reply.speech ?? "Request completed."}</p>
          {live.reply.voice_error && <p>Spoken response unavailable: {live.reply.voice_error}</p>}
        </div>
      ) : (
        <Empty icon="assistant" title="Ready when you are">
          Your next answer will appear here.
        </Empty>
      )}
    </>
  );
  return (
    <div
      ref={workspace}
      className={`optis-workspace ${preferences.text === "large" ? "o-large" : ""} ${preferences.contrast ? "o-contrast" : ""} ${preferences.motion ? "o-reduced" : ""}`}
    >
      <a className="o-skip" href="#workspace-content">
        Skip to content
      </a>
      <aside className="o-sidebar">
        <button className="o-wordmark" onClick={() => go("Home")} aria-label="OPTIS home">
          <span className="o-logo-mark">
            <i />
            <i />
          </span>
          OPTIS
        </button>
        <span className="o-sidebar-label">YOUR WORKSPACE</span>
        <nav aria-label="Primary navigation">
          {pages.map((p) => (
            <a
              key={p.name}
              aria-label={p.name}
              href={`#/app/${p.name.toLowerCase()}`}
              onClick={(e) => {
                e.preventDefault();
                go(p.name);
              }}
              className={page === p.name ? "is-selected" : ""}
              aria-current={page === p.name ? "page" : undefined}
            >
              <Icon name={p.icon} />
              <span>{p.name}</span>
              {page === p.name && <span className="o-nav-dot" />}
            </a>
          ))}
        </nav>
      </aside>
      <div className="o-main">
        <header className="o-topbar">
          <span>
            Workspace <span className="o-breadcrumb">/ {page}</span>
          </span>
          <div className="o-header-tools">
            <button
              className="o-audio-access"
              onClick={() => setAudioOpen(true)}
              aria-haspopup="dialog"
            >
              <Icon name="mic" />
              Voice &amp; Audio
            </button>
            <button className="o-connection-control" onClick={() => go("Settings")}>
              <Icon name="settings" size={16} />
              System Status
            </button>
            <button
              className="o-header-back"
              onClick={() => {
                actions?.onLeave?.();
                history.replaceState(null, "", location.pathname + location.search);
                setPage("Home");
                exit();
              }}
            >
              Back to experience <Icon name="arrow" size={16} />
            </button>
          </div>
        </header>
        <main id="workspace-content" className="o-content" tabIndex={-1}>
          <div className="o-page-heading">
            <div>
              <p className="o-eyebrow">
                {page === "Home" ? "A NEW PERSPECTIVE" : `OPTIS / ${page.toUpperCase()}`}
              </p>
              <h1 ref={heading} tabIndex={-1}>
                {pageInfo.title}
              </h1>
              <p>{pageInfo.subtitle}</p>
            </div>
            <span className="o-page-number">
              0{pages.findIndex((p) => p.name === page) + 1}
              <span> / 05</span>
            </span>
          </div>
          {(live.error || validation) && (
            <div className="o-notice o-error" role="alert">
              <span>{validation || live.error}</span>
              <button
                onClick={() => {
                  setValidation("");
                  live.setError("");
                }}
                aria-label="Dismiss message"
              >
                <Icon name="close" />
              </button>
            </div>
          )}
          {live.busy && (
            <div className="o-notice" role="status">
              Working on your request…
            </div>
          )}
          <div
            className="o-sr-status"
            role={preferences.announcements ? "status" : undefined}
            aria-atomic="true"
          >
            {live.reply?.text ?? live.reply?.speech ?? ""}
          </div>
          {page === "Home" && (
            <>
              <section className="o-home-hero">
                <div>
                  <span className="o-kicker">A LITTLE MORE AWARE. A LITTLE MORE INDEPENDENT.</span>
                  <h2>
                    Your world.
                    <br />
                    <span>A little clearer.</span>
                  </h2>
                  <p>
                    Understand the view. Find the everyday.
                    <br />
                    Take your next step with intention.
                  </p>
                  <button className="o-hero-link" onClick={() => setAudioOpen(true)}>
                    Speak to OPTIS
                    <Icon name="arrow" />
                  </button>
                </div>
                <OpticsArt />
                <span className="o-art-caption">AWARENESS, THROUGH A DIFFERENT LENS.</span>
              </section>
              <Panel title="Quick Actions">
                <div className="o-quick-grid">
                  {[
                    {
                      label: "Describe My Surroundings",
                      icon: "scene" as IconName,
                      run: () => {
                        go("Assistant");
                        void act("Describe my surroundings", { kind: "scene" });
                      },
                    },
                    {
                      label: "Find My Keys",
                      icon: "keys" as IconName,
                      run: () => {
                        go("Vision", "Find Objects");
                        setCategory("keyring");
                        void act("Find my keys", { kind: "find", item: "keys" });
                      },
                    },
                    {
                      label: "Find My Phone",
                      icon: "phone" as IconName,
                      run: () => {
                        go("Vision", "Find Objects");
                        setCategory("cell phone");
                        void act("Find my phone", { kind: "find", item: "phone" });
                      },
                    },
                    {
                      label: "Find My Bottle",
                      icon: "bottle" as IconName,
                      run: () => {
                        go("Vision", "Find Objects");
                        setCategory("bottle");
                        void act("Find my bottle", { kind: "find", item: "bottle" });
                      },
                    },
                    {
                      label: "Walk to a Destination",
                      icon: "navigate" as IconName,
                      run: () => go("Navigate"),
                    },
                    {
                      label: "Record a Voice Command",
                      icon: "mic" as IconName,
                      run: () => setAudioOpen(true),
                    },
                  ].map((a) => (
                    <button
                      className="o-quick"
                      key={a.label}
                      onClick={a.run}
                      disabled={live.busy || voiceBusy}
                    >
                      <span className="o-quick-icon">
                        <Icon name={a.icon} size={23} />
                      </span>
                      <span>{a.label}</span>
                      <Icon name="arrow" size={17} />
                    </button>
                  ))}
                </div>
              </Panel>
              <div className="o-two-col">
                <Panel title="System At a Glance">
                  <div className="o-system-list">
                    {systemRows.map(([label, value], i) => (
                      <div key={label}>
                        <Icon
                          name={
                            (["settings", "vision", "mic", "phone", "navigate"] as IconName[])[i]
                          }
                        />
                        <strong>{label}</strong>
                        <span>{value}</span>
                      </div>
                    ))}
                  </div>
                  <button className="o-text-link" onClick={() => go("Settings")}>
                    System Diagnostics <Icon name="arrow" />
                  </button>
                </Panel>
                <Panel title="Latest Result">{lastResult}</Panel>
              </div>
              {routeActive && (
                <Panel
                  title="Current Route"
                  aside={
                    <span className="o-tag">
                      {simulated ? "DEMO ROUTE" : paused ? "ROUTE PAUSED" : "LIVE GPS"}
                    </span>
                  }
                >
                  <p>{route?.text ?? "Waiting for the next instruction."}</p>
                  {routeButtons}
                </Panel>
              )}
            </>
          )}
          {page === "Assistant" && (
            <>
              <div className="o-two-col o-assistant-grid">
                <Panel
                  title="Command Conversation"
                  aside={<span className="o-tag">Supported commands</span>}
                >
                  <div className="o-conversation">
                    <span className="o-assistant-orb">
                      <Icon name="assistant" size={32} />
                    </span>
                    {!live.events.length ? (
                      <>
                        <h3>
                          A clear request.
                          <br />A useful next step.
                        </h3>
                        <p>
                          Describe a scene. Find an item.
                          <br />
                          Choose your next destination.
                        </p>
                      </>
                    ) : (
                      <div className="o-messages">
                        {live.events.slice(-6).map((e) => (
                          <div key={e.id}>
                            <strong>{e.title}</strong>
                            <p>{e.text}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <form
                    className="o-composer"
                    onSubmit={(e) => {
                      e.preventDefault();
                      submitCommand();
                    }}
                  >
                    <label htmlFor="command">Your Request</label>
                    <div>
                      <input
                        id="command"
                        value={requestText}
                        maxLength={300}
                        onChange={(e) => setRequestText(e.target.value)}
                        placeholder="Try “What is ahead?”"
                        aria-describedby="command-help"
                      />
                      <button
                        type="submit"
                        aria-label="Send supported command"
                        disabled={!requestText.trim() || !canAct}
                      >
                        <Icon name="arrow" />
                      </button>
                    </div>
                    <p id="command-help">Scene descriptions, item lookup and walking navigation.</p>
                  </form>
                  <div className="o-chips">
                    {["What’s ahead?", "Find my phone", "Pause route"].map((c) => (
                      <button key={c} onClick={() => setRequestText(c)}>
                        {c}
                      </button>
                    ))}
                  </div>
                </Panel>
                <div className="o-stack">
                  <Panel title="Voice Commands">{voiceControls}</Panel>
                  <Panel title="Try Saying">
                    <ul className="o-phrase-list">
                      {[
                        "What do you see?",
                        "Find my keys",
                        "Find my bottle",
                        "Walk to [place]",
                        "Choose first",
                        "Pause route",
                        "Resume route",
                        "Stop navigation",
                        "Recalculate route",
                      ].map((c) => (
                        <li key={c}>
                          <button onClick={() => setRequestText(c)}>
                            {c}
                            <Icon name="plus" size={15} />
                          </button>
                        </li>
                      ))}
                    </ul>
                  </Panel>
                </div>
              </div>
              <Panel
                title="Recent Session Actions"
                aside={
                  live.events.length > 0 && (
                    <button className="o-text-link" onClick={live.clearEvents}>
                      Clear session
                    </button>
                  )
                }
              >
                {live.events.length ? (
                  <ol className="o-activity">
                    {live.events
                      .slice()
                      .reverse()
                      .map((e) => (
                        <li key={e.id}>
                          <Icon name="clock" />
                          <div>
                            <strong>{e.title}</strong>
                            <p>{e.text}</p>
                          </div>
                          <time>{e.time}</time>
                        </li>
                      ))}
                  </ol>
                ) : (
                  <p>No requests yet.</p>
                )}
                <p className="o-footnote">Session activity is cleared when you disconnect.</p>
              </Panel>
            </>
          )}
          {page === "Vision" && (
            <>
              <div className="o-tabs" aria-label="Vision sections">
                {["Live Camera", "Scene Awareness", "Find Objects", "Item Memory"].map((t) => (
                  <button
                    key={t}
                    className={visionTab === t ? "is-selected" : ""}
                    aria-pressed={visionTab === t}
                    onClick={() => setVisionTab(t)}
                  >
                    {t}
                  </button>
                ))}
              </div>
              {visionTab === "Live Camera" && (
                <div className="o-two-col o-vision-grid">
                  <Panel
                    title="Live Camera"
                    aside={
                      <span className="o-tag">
                        {live.preview?.state?.replace(/_/g, " ") ??
                          (live.previewing ? "Loading…" : "Preview stopped")}
                      </span>
                    }
                  >
                    {live.preview?.image &&
                    live.preview.observation &&
                    live.preview.state === "ready" ? (
                      <CameraFrame frame={live.preview} labels={preferences.labels} />
                    ) : (
                      <div className="o-camera-empty">
                        <Empty
                          icon="vision"
                          title={live.previewing ? "Waiting for the camera" : "Your camera view"}
                        >
                          {live.cameraError ||
                            (live.health?.camera === "disabled"
                              ? "A camera is not available on this OPTIS system."
                              : live.previewing
                                ? "The camera is not providing a fresh frame."
                                : "Your camera view and object descriptions appear here.")}
                        </Empty>
                      </div>
                    )}
                    <div className="o-actions">
                      <Button
                        primary
                        disabled={
                          !live.ready || live.previewing || live.health?.camera === "disabled"
                        }
                        onClick={() => live.setPreviewing(true)}
                      >
                        Start Preview
                      </Button>
                      <Button disabled={!live.previewing} onClick={() => live.setPreviewing(false)}>
                        Stop Preview
                      </Button>
                    </div>
                    <Toggle
                      label="Show Detection Labels"
                      detail="Display boxes and labels over the current camera frame."
                      checked={preferences.labels}
                      change={() => update("labels", !preferences.labels)}
                    />
                  </Panel>
                  <div className="o-stack">
                    <Panel title="Camera Status">
                      <dl className="o-mini-data">
                        <div>
                          <dt>Camera</dt>
                          <dd>{live.ready ? (live.health?.camera ?? "—") : "—"}</dd>
                        </div>
                        <div>
                          <dt>Source</dt>
                          <dd>{live.preview?.observation?.source ?? "—"}</dd>
                        </div>
                        <div>
                          <dt>Frame</dt>
                          <dd>{live.preview?.observation?.frame_id ?? "—"}</dd>
                        </div>
                        <div>
                          <dt>Resolution</dt>
                          <dd>{live.preview?.observation?.size_px?.join(" × ") ?? "—"}</dd>
                        </div>
                      </dl>
                    </Panel>
                    <Panel title="Objects in View">
                      {live.preview?.state === "ready" &&
                      live.preview.observation?.detections.filter((d) => d.stable).length ? (
                        <ul className="o-detections">
                          {live.preview.observation.detections
                            .filter((d) => d.stable)
                            .map((d, i) => (
                              <li key={i}>
                                <strong>{d.label}</strong>
                                <span>
                                  {d.position} of camera view · {Math.round(d.confidence * 100)}%
                                </span>
                              </li>
                            ))}
                        </ul>
                      ) : (
                        <p>No stable detections to show.</p>
                      )}
                    </Panel>
                  </div>
                </div>
              )}
              {visionTab === "Scene Awareness" && (
                <div className="o-two-col">
                  <Panel title="Scene Awareness">
                    <h3>What OPTIS Sees</h3>
                    {lastResult}
                    <div className="o-actions">
                      <Button
                        primary
                        disabled={!canAct || !cameraReady}
                        onClick={() => void act("What’s ahead?", { kind: "scene" })}
                      >
                        What’s ahead?
                      </Button>
                      <Button
                        disabled={!canAct || !cameraReady}
                        onClick={() => void act("Refresh scene", { kind: "scene" })}
                      >
                        Refresh Scene
                      </Button>
                    </div>
                    {!cameraReady && <p>Scene descriptions require a fresh camera view.</p>}
                  </Panel>
                  <Panel title="Camera-relative awareness">
                    <Icon name="vision" size={38} />
                    <h3>A direction in the image.</h3>
                    <p>
                      Left, center and right describe the camera view. They do not confirm distance,
                      obstacle clearance or a safe walking path.
                    </p>
                  </Panel>
                </div>
              )}
              {visionTab === "Find Objects" && (
                <>
                  <Panel title="Find Objects">
                    <h3>Find an Object</h3>
                    <p>
                      Browse the camera’s recognizable categories. Keys use an optional keyring
                      detector.
                    </p>
                    <label className="o-field">
                      Search detection categories
                      <input
                        value={filter}
                        onChange={(e) => setFilter(e.target.value)}
                        placeholder="Try chair, person, backpack…"
                      />
                    </label>
                    <div className="o-class-grid" aria-label="Model detection categories">
                      {[...modelClasses, "keyring"]
                        .filter((c) => c.includes(filter.trim().toLowerCase()))
                        .map((c) => (
                          <button
                            key={c}
                            aria-pressed={objectClass === c}
                            className={objectClass === c ? "is-selected" : ""}
                            onClick={() => setCategory(c)}
                          >
                            <Icon
                              name={
                                c === "cell phone"
                                  ? "phone"
                                  : c === "bottle"
                                    ? "bottle"
                                    : c === "keyring"
                                      ? "keys"
                                      : "vision"
                              }
                            />
                            {c}
                          </button>
                        ))}
                    </div>
                    {![...modelClasses, "keyring"].some((c) =>
                      c.includes(filter.trim().toLowerCase()),
                    ) && <p role="status">No matching category.</p>}
                    <div className="o-selected-object">
                      <h3>{objectClass}</h3>
                      <p>
                        {lookupSupported
                          ? "Find a current match, or check its last-seen or saved location."
                          : "This category can appear in scene observations. Use a scene description to understand the current view."}
                      </p>
                    </div>
                    <div className="o-actions">
                      <Button
                        primary
                        disabled={!canAct || (!lookupSupported && !cameraReady)}
                        onClick={() =>
                          void act(
                            lookupSupported ? `Find ${item}` : "Describe the scene",
                            lookupSupported ? { kind: "find", item } : { kind: "scene" },
                          )
                        }
                      >
                        {lookupSupported ? `Find ${item}` : "Describe the Scene"}
                      </Button>
                      {lookupSupported && (
                        <Button onClick={() => go("Vision", "Item Memory")}>
                          Manage Saved Location
                        </Button>
                      )}
                    </div>
                  </Panel>
                  <Panel title="Search Result">
                    {lastResult}
                    <p className="o-footnote">
                      Live observations, previous sightings and saved placements are distinct. A
                      keyring detection cannot establish ownership.
                    </p>
                  </Panel>
                </>
              )}
              {visionTab === "Item Memory" && (
                <div className="o-two-col">
                  <Panel title="Item Memory">
                    <h3>Remember a Place</h3>
                    <form
                      onSubmit={async (e) => {
                        e.preventDefault();
                        if (!place.trim()) return;
                        const r = await act(`Remember ${item}`, {
                          kind: "remember",
                          item,
                          place: place.trim(),
                        });
                        if (r?.status === "saved_placement") setPlace("");
                      }}
                    >
                      {itemSelect}
                      <label className="o-field">
                        Where did you leave it?
                        <input
                          value={place}
                          maxLength={300}
                          onChange={(e) => setPlace(e.target.value)}
                          placeholder="e.g. In the drawer by the door"
                          required
                        />
                      </label>
                      <div className="o-actions">
                        <button
                          className="o-button o-primary"
                          type="submit"
                          disabled={!canAct || !place.trim()}
                        >
                          Remember Location
                        </button>
                        <Button
                          disabled={!canAct}
                          onClick={() => void act(`Find ${item}`, { kind: "find", item })}
                        >
                          Find Item
                        </Button>
                      </div>
                    </form>
                    <h3 className="o-section-gap">Forget an Item</h3>
                    <p>Remove its saved placement and automatic sightings.</p>
                    <Button disabled={!canAct} onClick={() => setForgetItem(item)}>
                      Forget Saved Information
                    </Button>
                  </Panel>
                  <div className="o-stack">
                    <Panel title="Saved Item Locations">
                      {lastResult}
                      <p className="o-footnote">
                        Look up one item at a time to see its current result. Saved locations are
                        the places you explicitly provided.
                      </p>
                    </Panel>
                    <Panel title="Recent Sightings">
                      <p>
                        A sighting identifies the camera and time of observation. It is not an exact
                        location or photograph.
                      </p>
                    </Panel>
                    <Panel title="Your Memory Is Private">
                      <p>
                        Saved placements and sightings are kept on your OPTIS system. Forget an item
                        to remove both.
                      </p>
                    </Panel>
                  </div>
                </div>
              )}
            </>
          )}
          {page === "Navigate" && (
            <>
              <div className="o-two-col o-navigation-grid">
                <div className="o-stack">
                  <Panel title="Destination Search">
                    <h3>Walk to a Destination</h3>
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        setMatches([]);
                        void act(`Find destination: ${query.trim()}`, {
                          kind: "find_destination",
                          query: query.trim(),
                        });
                      }}
                    >
                      <label className="o-field">
                        Name, address, or latitude, longitude
                        <div className="o-search">
                          <Icon name="search" />
                          <input
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            maxLength={200}
                            placeholder="Where would you like to go?"
                            required
                          />
                        </div>
                      </label>
                      <button
                        type="submit"
                        className="o-button o-primary"
                        disabled={
                          !canAct || !live.health?.pedestrian_routing_configured || !query.trim()
                        }
                      >
                        Find Destination
                      </button>
                    </form>
                    {live.ready && !live.health?.pedestrian_routing_configured && (
                      <p>Walking route search is unavailable on this OPTIS system.</p>
                    )}
                    {matches.length > 0 &&
                      (now < expires ? (
                        <ol className="o-destination-list">
                          {matches.map((d, i) => (
                            <li key={`${d.lat}-${d.lon}-${i}`}>
                              <Button
                                disabled={!canAct || !gps?.ready}
                                onClick={() =>
                                  void act(`Walk to ${d.name}`, { kind: "walk_to", destination: d })
                                }
                              >
                                {d.name}
                                <Icon name="arrow" size={16} />
                              </Button>
                              <p className="o-footnote">
                                {d.lat.toFixed(5)}, {d.lon.toFixed(5)}
                              </p>
                            </li>
                          ))}
                        </ol>
                      ) : (
                        <p>Destination choices expired. Search again.</p>
                      ))}
                    {matches.length > 0 && !gps?.ready && (
                      <p>Share a fresh, accurate location before choosing a destination.</p>
                    )}
                  </Panel>
                  <Panel
                    title="Active Route"
                    aside={
                      routeActive && (
                        <span className="o-tag">
                          {simulated ? "DEMO ROUTE" : paused ? "ROUTE PAUSED" : "LIVE GPS"}
                        </span>
                      )
                    }
                  >
                    <h3>Current Instruction</h3>
                    <p>{route?.text ?? route?.status?.replace(/_/g, " ") ?? "No route started."}</p>
                    {routeButtons}
                  </Panel>
                </div>
                <Panel
                  title="Route Preview"
                  aside={<span className="o-tag">NORTH-UP SCHEMATIC</span>}
                >
                  {live.status?.route_map ? (
                    <RoutePreview route={live.status.route_map} />
                  ) : (
                    <div className="o-map-empty">
                      <span className="o-north">N ↑</span>
                      <Empty icon="navigate" title="Your next direction starts here.">
                        Choose a destination to see your route. Demo replay does not provide a
                        mapped route preview.
                      </Empty>
                    </div>
                  )}
                </Panel>
              </div>
              <div className="o-three-col">
                <Panel title="GPS Status">
                  <h3>
                    {gps?.ready
                      ? "Location ready"
                      : gps
                        ? gps.age_seconds > 5
                          ? "Location is stale"
                          : "Location accuracy is too low"
                        : "No location received"}
                  </h3>
                  <dl className="o-mini-data">
                    <div>
                      <dt>Fix age</dt>
                      <dd>{gps ? `${gps.age_seconds.toFixed(1)} s` : "—"}</dd>
                    </div>
                    <div>
                      <dt>Accuracy</dt>
                      <dd>{gps ? `±${gps.horizontal_accuracy_m.toFixed(1)} m` : "—"}</dd>
                    </div>
                  </dl>
                  <div className="o-actions">
                    <Button
                      disabled={!live.ready || !actions?.onStartLocation || media.sharing}
                      onClick={media.startLocation}
                    >
                      Use my location
                    </Button>
                    <Button disabled={!media.sharing} onClick={() => media.stopLocation()}>
                      Stop Sharing
                    </Button>
                  </div>
                  <p role="status">{media.locationMessage}</p>
                  <p className="o-footnote">
                    Keep this page open while sharing. Location access requires your permission.
                  </p>
                </Panel>
                <Panel title="Demo Routes" aside={<span className="o-tag">SIMULATION</span>}>
                  <p>
                    Explore repeatable route guidance with a standard or weak-GPS replay. This is
                    not live walking guidance.
                  </p>
                  <div className="o-actions">
                    <Button
                      disabled={!canAct}
                      onClick={() =>
                        void act("Start demo route", { kind: "start_route", route_id: "standard" })
                      }
                    >
                      Start Demo Route
                    </Button>
                    <Button
                      disabled={!canAct}
                      onClick={() =>
                        void act("Replay weak GPS", { kind: "start_route", route_id: "noisy" })
                      }
                    >
                      Replay Weak GPS
                    </Button>
                    <Button
                      disabled={!canAct || !routeActive || !simulated || paused}
                      onClick={() => void act("Next demo step", { kind: "next" })}
                    >
                      Next Demo Step
                    </Button>
                    {live.health?.live_route_configured && (
                      <Button
                        disabled={!canAct || !live.health.live_route_id}
                        onClick={() =>
                          void act("Start checked route", {
                            kind: "start_route",
                            route_id: live.health!.live_route_id!,
                          })
                        }
                      >
                        Start Checked Route
                      </Button>
                    )}
                  </div>
                </Panel>
                <Panel title="Spoken Cues">
                  <Icon name="sound" size={30} />
                  <Toggle
                    label="Play spoken route cues"
                    detail={
                      voiceReady
                        ? "Hear navigation audio from OPTIS."
                        : "Speech service is unavailable."
                    }
                    checked={preferences.playback}
                    change={() => update("playback", !preferences.playback)}
                  />
                  {media.audioSource && <Button onClick={media.playResponse}>Play Response</Button>}
                </Panel>
              </div>
              <p className="o-safety">
                <Icon name="shield" />
                Walking directions are experimental. They do not confirm obstacle clearance,
                crossings, or entrances. Supervised testing only.
              </p>
            </>
          )}
          {page === "Settings" && (
            <div className="o-two-col">
              <div className="o-stack">
                <Panel title="Accessibility">
                  <label className="o-field">
                    Text size
                    <select
                      value={preferences.text}
                      onChange={(e) => update("text", e.target.value as Preferences["text"])}
                    >
                      <option value="standard">Standard</option>
                      <option value="large">Large</option>
                    </select>
                  </label>
                  <Toggle
                    label="Higher contrast"
                    checked={preferences.contrast}
                    change={() => update("contrast", !preferences.contrast)}
                  />
                  <Toggle
                    label="Reduce motion"
                    detail="Your device’s reduced-motion preference is also respected."
                    checked={preferences.motion}
                    change={() => update("motion", !preferences.motion)}
                  />
                  <Toggle
                    label="Screen reader announcements"
                    detail="Announce responses and interface messages."
                    checked={preferences.announcements}
                    change={() => update("announcements", !preferences.announcements)}
                  />
                  <p className="o-footnote">Preferences are saved on this browser.</p>
                </Panel>
                <Panel title="Audio & Voice">
                  {voiceControls}
                  <p className="o-footnote">
                    Recordings are sent to xAI for speech processing. OPTIS supports focused
                    commands for scene awareness, item lookup and navigation.
                  </p>
                </Panel>
                <Panel title="Camera & Vision">
                  <p>Camera: {live.ready ? (live.health?.camera ?? "—") : "—"}</p>
                  <Toggle
                    label="Show Detection Labels"
                    checked={preferences.labels}
                    change={() => update("labels", !preferences.labels)}
                  />
                  <Button onClick={() => go("Vision", "Live Camera")}>Open Live Camera</Button>
                </Panel>
                <Panel title="GPS & Navigation">
                  <h3>Use your phone’s location</h3>
                  <p>
                    Open OPTIS on your phone, choose Use my location, and allow precise location
                    access. Keep the page open while you walk. Wait for a fresh, accurate fix before
                    choosing a destination.
                  </p>
                  <p className="o-footnote">
                    Share location only on a device you intend to use for navigation. Sharing stops
                    when this page is hidden or you disconnect.
                  </p>
                  <div className="o-actions">
                    <Button
                      disabled={!live.ready || !actions?.onStartLocation || media.sharing}
                      onClick={media.startLocation}
                    >
                      Use my location
                    </Button>
                    <Button disabled={!media.sharing} onClick={() => media.stopLocation()}>
                      Stop Sharing
                    </Button>
                  </div>
                  <p role="status">{media.locationMessage}</p>
                </Panel>
              </div>
              <div className="o-stack">
                <Panel title="System Diagnostics">
                  <h3>System Overview</h3>
                  <dl className="o-mini-data">
                    {systemRows.map(([label, value]) => (
                      <div key={label}>
                        <dt>{label}</dt>
                        <dd>{value}</dd>
                      </div>
                    ))}
                    <div>
                      <dt>Navigation Audio</dt>
                      <dd>
                        {live.status?.audio.audio_error
                          ? "Unavailable"
                          : voiceReady
                            ? "Available"
                            : "Unavailable"}
                      </dd>
                    </div>
                    <div>
                      <dt>Robotic Arm</dt>
                      <dd>Disabled</dd>
                    </div>
                  </dl>
                </Panel>
                <Panel title="Privacy & Data">
                  <Icon name="shield" size={29} />
                  <h3>Your information has context.</h3>
                  <p>
                    Saved placements and camera sightings are kept on your OPTIS system. Sighting
                    records contain metadata, not photos. Forgetting an item clears its saved place
                    and sightings.
                  </p>
                  <p>
                    Voice recordings and response text are processed by xAI when you use voice.
                    Location sharing supplies this device’s current fix for navigation. Share
                    location and audio only when you choose to use those features.
                  </p>
                  <Button onClick={() => go("Vision", "Item Memory")}>
                    Manage Item Memory <Icon name="arrow" />
                  </Button>
                </Panel>
                <Panel title="About OPTIS">
                  <span className="o-about-brand">OPTIS</span>
                  <p>Awareness, guidance, and the things that matter.</p>
                  <p>
                    Camera-relative awareness, personal-item lookup and experimental walking
                    guidance. OPTIS does not confirm obstacle clearance or safe crossings.
                  </p>
                </Panel>
              </div>
            </div>
          )}
          <footer className="o-footer">
            <span>Designed around your everyday.</span>
            <span>
              OPTIS <span>—</span> A DIFFERENT PERSPECTIVE
            </span>
          </footer>
        </main>
      </div>
      <dialog
        ref={audioDialog}
        className="o-dialog o-audio-dialog"
        aria-labelledby="audio-title"
        onCancel={() => setAudioOpen(false)}
        onClose={() => setAudioOpen(false)}
      >
        <div className="o-panel-heading">
          <h2 id="audio-title">Voice &amp; Audio</h2>
          <Button onClick={() => setAudioOpen(false)}>
            <span className="o-sr-only">Close voice and audio</span>
            <Icon name="close" />
          </Button>
        </div>
        {voiceControls}
        <details className="o-contract">
          <summary>Using OPTIS without sight</summary>
          <ol className="o-voice-steps">
            <li>Use your screen reader or keyboard to reach Voice &amp; Audio.</li>
            <li>Choose Start Speaking. Your screen reader announces the recording state.</li>
            <li>
              Speak a command, then choose Stop &amp; Ask. The response appears when it is ready.
            </li>
            <li>
              Hear the response or use Play Response. Text remains available to your screen reader.
            </li>
          </ol>
          <p>Press Stop &amp; Ask when you finish your command.</p>
        </details>
        <Toggle
          label="Screen reader announcements"
          checked={preferences.announcements}
          change={() => update("announcements", !preferences.announcements)}
        />
      </dialog>
      <dialog
        ref={forgetDialog}
        className="o-dialog"
        aria-labelledby="forget-title"
        onCancel={() => setForgetItem(null)}
        onClose={() => setForgetItem(null)}
      >
        <h2 id="forget-title">Forget saved information for {forgetItem}?</h2>
        <p>This removes both the saved placement and camera sightings for this item.</p>
        <div className="o-actions">
          <Button onClick={() => setForgetItem(null)}>Cancel</Button>
          <Button
            disabled={!canAct}
            onClick={async () => {
              const target = forgetItem;
              if (!target) return;
              const r = await act(`Forget ${target}`, { kind: "forget", item: target });
              if (r) setForgetItem(null);
            }}
          >
            Forget Saved Information
          </Button>
        </div>
      </dialog>
    </div>
  );
}
