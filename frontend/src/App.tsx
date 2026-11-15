import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Red-lens center measured from frontend/public/optis-glasses.png (1078×375).
 * The tight red circle bounding box is x 997–1010, y 76–92.
 * Center (1003.5, 84). Diameter 16px. Do not retune without remeasuring the asset.
 */
const SOURCE_WIDTH = 1078;
const LENS_X = 1003.5 / SOURCE_WIDTH;
const LENS_Y = 84 / 375;
const LENS_DIAMETER = 16 / SOURCE_WIDTH;

const DURATION_MS = 1400;

type Phase = "idle" | "approach" | "enter_lens" | "reveal_app" | "app_ready";

type LensGeometry = {
  lensX: number;
  lensY: number;
  lensD: number;
  originX: number;
  originY: number;
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function smooth(value: number) {
  const t = clamp(value, 0, 1);
  return t * t * (3 - 2 * t);
}

function phaseFor(progress: number): Phase {
  if (progress <= 0) return "idle";
  if (progress < 0.55) return "approach";
  if (progress < 0.85) return "enter_lens";
  if (progress < 1) return "reveal_app";
  return "app_ready";
}

function measureLens(image: HTMLImageElement): LensGeometry | null {
  if (!image.naturalWidth || image.clientWidth === 0) return null;

  const rect = image.getBoundingClientRect();
  const fitted = Math.min(rect.width / image.naturalWidth, rect.height / image.naturalHeight);
  const drawnWidth = image.naturalWidth * fitted;
  const drawnHeight = image.naturalHeight * fitted;
  const offsetX = (rect.width - drawnWidth) / 2;
  const offsetY = (rect.height - drawnHeight) / 2;
  const lensX = rect.left + offsetX + LENS_X * drawnWidth;
  const lensY = rect.top + offsetY + LENS_Y * drawnHeight;

  return {
    lensX,
    lensY,
    lensD: Math.max(LENS_DIAMETER * drawnWidth, 1),
    originX: lensX - rect.left,
    originY: lensY - rect.top,
  };
}

export default function App() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [reducedEntry, setReducedEntry] = useState(false);
  const phaseRef = useRef<Phase>("idle");
  const frameRef = useRef<number | null>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const opticsRef = useRef<HTMLDivElement>(null);
  const veilRef = useRef<HTMLDivElement>(null);
  const chromeRef = useRef<HTMLDivElement>(null);
  const spotlightRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<HTMLElement>(null);
  const geometryRef = useRef<LensGeometry | null>(null);

  const setPhaseBoth = useCallback((next: Phase) => {
    phaseRef.current = next;
    setPhase(next);
  }, []);

  const clearMotion = useCallback(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
    const image = imageRef.current;
    const optics = opticsRef.current;
    const veil = veilRef.current;
    const chrome = chromeRef.current;
    const spotlight = spotlightRef.current;
    const app = appRef.current;
    if (image) {
      image.style.transform = "";
      image.style.transformOrigin = "";
      image.style.opacity = "";
    }
    if (optics) {
      optics.style.transform = "";
      optics.style.opacity = "";
      optics.style.left = "";
      optics.style.top = "";
      optics.style.width = "";
      optics.style.height = "";
    }
    if (veil) veil.style.opacity = "";
    if (chrome) chrome.style.opacity = "";
    if (spotlight) spotlight.style.opacity = "";
    if (app) app.style.opacity = "";
    geometryRef.current = null;
  }, []);

  const applyFrame = useCallback((progress: number, geometry: LensGeometry) => {
    const image = imageRef.current;
    const optics = opticsRef.current;
    const veil = veilRef.current;
    const chrome = chromeRef.current;
    const spotlight = spotlightRef.current;
    const app = appRef.current;
    if (!image || !optics || !veil || !chrome || !spotlight || !app) return;

    const center = smooth((progress - 0.15) / 0.4);
    const scaleT = smooth((progress - 0.05) / 0.95);
    const targetLens = Math.min(window.innerWidth, window.innerHeight) * 0.46;
    const scaleMax = clamp(targetLens / geometry.lensD, 10, 26);
    const scale = 1 + (scaleMax - 1) * scaleT;
    const translateX = (window.innerWidth / 2 - geometry.lensX) * center;
    const translateY = (window.innerHeight / 2 - geometry.lensY) * center;
    const opticSize = geometry.lensD * 0.82;
    const cover = Math.hypot(window.innerWidth, window.innerHeight) * 1.08;
    const expansionNeed = cover / (opticSize * scale);
    const expansion = 1 + (expansionNeed - 1) * smooth((progress - 0.52) / 0.26);

    image.style.transformOrigin = `${geometry.originX}px ${geometry.originY}px`;
    image.style.transform = `translate3d(${translateX}px, ${translateY}px, 0) scale(${scale})`;

    optics.style.transform = `translate3d(${translateX}px, ${translateY}px, 0) scale(${scale * expansion})`;
    optics.style.opacity = String(smooth((progress - 0.52) / 0.1));
    veil.style.opacity = String(smooth((progress - 0.74) / 0.12));

    const chromeOpacity = 1 - smooth(progress / 0.15);
    chrome.style.opacity = String(chromeOpacity);
    spotlight.style.opacity = String(chromeOpacity);
    app.style.opacity = String(smooth((progress - 0.86) / 0.14));
  }, []);

  const finish = useCallback(
    (next: Phase) => {
      frameRef.current = null;
      setPhaseBoth(next);
    },
    [setPhaseBoth],
  );

  const startTransition = useCallback(() => {
    if (phaseRef.current !== "idle" || frameRef.current !== null) return;
    phaseRef.current = "approach";

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      clearMotion();
      setReducedEntry(true);
      setPhaseBoth("app_ready");
      return;
    }

    const image = imageRef.current;
    const geometry = image ? measureLens(image) : null;
    if (!image || !geometry) {
      phaseRef.current = "idle";
      return;
    }

    geometryRef.current = geometry;
    const opticSize = geometry.lensD * 0.82;
    const optics = opticsRef.current;
    if (optics) {
      optics.style.left = `${geometry.lensX - opticSize / 2}px`;
      optics.style.top = `${geometry.lensY - opticSize / 2}px`;
      optics.style.width = `${opticSize}px`;
      optics.style.height = `${opticSize}px`;
    }

    setReducedEntry(false);
    setPhaseBoth("approach");
    const started = performance.now();

    const tick = (now: number) => {
      const progress = clamp((now - started) / DURATION_MS, 0, 1);
      applyFrame(progress, geometry);
      const next = phaseFor(progress);
      if (next !== phaseRef.current) setPhaseBoth(next);
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
        return;
      }
      applyFrame(1, geometry);
      finish("app_ready");
    };

    frameRef.current = requestAnimationFrame(tick);
  }, [applyFrame, clearMotion, finish, setPhaseBoth]);

  const returnToLanding = useCallback(() => {
    clearMotion();
    setReducedEntry(false);
    setPhaseBoth("idle");
  }, [clearMotion, setPhaseBoth]);

  useEffect(() => {
    const image = imageRef.current;
    if (!image) return;

    const warm = () => {
      if (phaseRef.current === "idle") geometryRef.current = measureLens(image);
    };
    if (image.complete) warm();
    image.addEventListener("load", warm);
    image.decode?.().then(warm).catch(() => undefined);

    const onResize = () => {
      if (phaseRef.current === "idle") warm();
    };
    window.addEventListener("resize", onResize);
    return () => {
      image.removeEventListener("load", warm);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  useEffect(() => {
    let touchStart = 0;
    let wheelDistance = 0;
    let wheelTimer: number | null = null;

    const onWheel = (event: WheelEvent) => {
      if (phaseRef.current !== "idle" || event.ctrlKey || event.deltaY <= 0) {
        wheelDistance = 0;
        return;
      }
      wheelDistance += event.deltaY;
      if (wheelDistance > 36) {
        wheelDistance = 0;
        startTransition();
      }
      if (wheelTimer !== null) window.clearTimeout(wheelTimer);
      wheelTimer = window.setTimeout(() => {
        wheelDistance = 0;
      }, 180);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (phaseRef.current !== "idle") return;
      if (!["ArrowDown", "PageDown", "Enter", " "].includes(event.key)) return;
      if (event.target instanceof HTMLButtonElement && (event.key === "Enter" || event.key === " ")) return;
      event.preventDefault();
      startTransition();
    };

    const onTouchStart = (event: TouchEvent) => {
      touchStart = event.touches[0]?.clientY ?? 0;
    };
    const onTouchEnd = (event: TouchEvent) => {
      if (phaseRef.current !== "idle") return;
      const touchEnd = event.changedTouches[0]?.clientY ?? touchStart;
      if (touchStart - touchEnd > 48) startTransition();
    };

    window.addEventListener("wheel", onWheel, { passive: true });
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchend", onTouchEnd, { passive: true });
    return () => {
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchend", onTouchEnd);
      if (wheelTimer !== null) window.clearTimeout(wheelTimer);
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    };
  }, [startTransition]);

  const inApp = phase === "app_ready";

  return (
    <div
      className={`landing${phase !== "idle" ? " is-diving" : ""}${inApp ? " is-app" : ""}${reducedEntry ? " is-reduced" : ""}`}
      data-phase={phase}
    >
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <div className="spotlight" ref={spotlightRef} aria-hidden="true" />

      <div className="chrome" ref={chromeRef} aria-hidden={phase !== "idle"}>
        <nav className="topbar" aria-label="Public navigation">
          <div className="wordmark">OPTIS</div>
          <button className="enter-button" type="button" onClick={startTransition}>
            Explore OPTIS
          </button>
        </nav>
        <main id="main-content" tabIndex={-1}>
          <h1 className="display-title">
            Your world. <span>Within reach.</span>
          </h1>
        </main>
      </div>

      <div className="spectacles-slot">
        <img
          ref={imageRef}
          src="/optis-glasses.png"
          alt="OPTIS spectacles with the ultrasonic sensor and camera module"
          draggable={false}
        />
      </div>

      <div className="optics" ref={opticsRef} aria-hidden="true">
        <div className="optics-veil" ref={veilRef} />
      </div>

      <section
        className="app-shell"
        ref={appRef}
        aria-hidden={!inApp}
        {...(inApp ? {} : { inert: true })}
      >
        <h2>OPTIS</h2>
        <p>Application ready</p>
        <button type="button" onClick={returnToLanding}>
          Return to landing
        </button>
      </section>
    </div>
  );
}
