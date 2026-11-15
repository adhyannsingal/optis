import {
  type CSSProperties,
  type RefObject,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

type ProductZoomConfig = {
  imageSrc: string;
  lensPoint: {
    x: number;
    y: number;
  };
  lensDiameterRatio: number;
  zoomScale: number;
  durationMs: number;
  destinationColor: string;
};

type LensGeometry = {
  lensViewportX: number;
  lensViewportY: number;
  originX: number;
  originY: number;
  translateX: number;
  translateY: number;
  lensDiameter: number;
  overlayScale: number;
};

type CameraZoomProperties = CSSProperties & {
  "--camera-origin-x": string;
  "--camera-origin-y": string;
  "--camera-translate-x": string;
  "--camera-translate-y": string;
  "--camera-lens-x": string;
  "--camera-lens-y": string;
  "--camera-lens-size": string;
  "--camera-overlay-scale": number;
  "--camera-fill-scale": number;
  "--camera-zoom-scale": number;
  "--camera-zoom-duration": string;
  "--camera-destination": string;
};

// The focal point was measured from the red circular lens in the 1078 × 375 source asset.
// Future hardware only needs a new source, normalized lens point, and optional scale tuning.
const productZoomConfig: ProductZoomConfig = {
  imageSrc: "/optis-glasses.png",
  lensPoint: {
    x: 0.9309,
    y: 0.2242,
  },
  lensDiameterRatio: 0.05,
  zoomScale: 15,
  durationMs: 1100,
  destinationColor: "#08090B",
};

function Spectacles({
  config,
  productRef,
  imageRef,
  lensAnchorRef,
  onImageLoad,
  zoomStyle,
}: {
  config: ProductZoomConfig;
  productRef: RefObject<HTMLDivElement | null>;
  imageRef: RefObject<HTMLImageElement | null>;
  lensAnchorRef: RefObject<HTMLSpanElement | null>;
  onImageLoad: () => void;
  zoomStyle?: CameraZoomProperties;
}) {
  return (
    <div className="spectacles" ref={productRef} style={zoomStyle}>
      <div className="spectacles-float">
        <img ref={imageRef} src={config.imageSrc} alt="" aria-hidden="true" onLoad={onImageLoad} />
        <span
          ref={lensAnchorRef}
          className="camera-lens-anchor"
          style={{
            left: `${config.lensPoint.x * 100}%`,
            top: `${config.lensPoint.y * 100}%`,
          }}
          aria-hidden="true"
        />
      </div>
    </div>
  );
}

function ProductIllustration({
  config,
  productRef,
  imageRef,
  lensAnchorRef,
  onImageLoad,
  zoomStyle,
}: {
  config: ProductZoomConfig;
  productRef: RefObject<HTMLDivElement | null>;
  imageRef: RefObject<HTMLImageElement | null>;
  lensAnchorRef: RefObject<HTMLSpanElement | null>;
  onImageLoad: () => void;
  zoomStyle?: CameraZoomProperties;
}) {
  return (
    <div className="product-illustration motion-stage">
      <div className="stage-word" aria-hidden="true">
        {"OPTIS".split("").map((letter, index) => (
          <span key={`${letter}-${index}`}>{letter}</span>
        ))}
      </div>
      <Spectacles
        config={config}
        productRef={productRef}
        imageRef={imageRef}
        lensAnchorRef={lensAnchorRef}
        onImageLoad={onImageLoad}
        zoomStyle={zoomStyle}
      />
    </div>
  );
}

function CameraZoomTransition({
  active,
  zoomStyle,
}: {
  active: boolean;
  zoomStyle?: CameraZoomProperties;
}) {
  return (
    <div
      className={`camera-zoom-transition ${active ? "is-active" : ""}`}
      style={zoomStyle}
      aria-hidden="true"
    >
      <div className="camera-dark-aperture">
        <div className="camera-dark-fill" />
      </div>
    </div>
  );
}

function OptisLanding({ enterApp }: { enterApp: () => void }) {
  const [zooming, setZooming] = useState(false);
  const [lensGeometry, setLensGeometry] = useState<LensGeometry | null>(null);
  const transitionStarted = useRef(false);
  const transitionTimer = useRef<number | null>(null);
  const pendingFrame = useRef<number | null>(null);
  const productRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const lensAnchorRef = useRef<HTMLSpanElement>(null);

  const measureLens = useCallback(() => {
    const product = productRef.current;
    const image = imageRef.current;
    const anchor = lensAnchorRef.current;
    if (!product || !image || !anchor || image.clientWidth === 0) return null;

    const productRect = product.getBoundingClientRect();
    const imageRect = image.getBoundingClientRect();
    const anchorRect = anchor.getBoundingClientRect();
    const lensViewportX = anchorRect.left + anchorRect.width / 2;
    const lensViewportY = anchorRect.top + anchorRect.height / 2;
    const lensDiameter = imageRect.width * productZoomConfig.lensDiameterRatio;

    const geometry: LensGeometry = {
      lensViewportX,
      lensViewportY,
      originX: lensViewportX - productRect.left,
      originY: lensViewportY - productRect.top,
      translateX: window.innerWidth / 2 - lensViewportX,
      translateY: window.innerHeight / 2 - lensViewportY,
      lensDiameter,
      overlayScale: (Math.hypot(window.innerWidth, window.innerHeight) / lensDiameter) * 1.08,
    };

    setLensGeometry(geometry);
    return geometry;
  }, []);

  useLayoutEffect(() => {
    const frame = window.requestAnimationFrame(measureLens);
    const onResize = () => {
      if (!transitionStarted.current) measureLens();
    };

    window.addEventListener("resize", onResize);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", onResize);
    };
  }, [measureLens]);

  const startTransition = useCallback(() => {
    if (transitionStarted.current || pendingFrame.current !== null) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reducedMotion) {
      transitionStarted.current = true;
      enterApp();
      return;
    }

    const attemptTransition = () => {
      pendingFrame.current = null;
      if (transitionStarted.current) return;

      const measuredGeometry = measureLens();
      if (!measuredGeometry) {
        pendingFrame.current = window.requestAnimationFrame(attemptTransition);
        return;
      }

      transitionStarted.current = true;
      setZooming(true);
      transitionTimer.current = window.setTimeout(enterApp, productZoomConfig.durationMs);
    };

    attemptTransition();
  }, [enterApp, measureLens]);

  useEffect(() => {
    let touchStart = 0;
    let wheelDistance = 0;
    let wheelResetTimer: number | null = null;

    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey) return;
      if (event.deltaY <= 0) {
        wheelDistance = 0;
        return;
      }

      wheelDistance += event.deltaY;
      if (wheelDistance > 28) startTransition();

      if (wheelResetTimer !== null) window.clearTimeout(wheelResetTimer);
      wheelResetTimer = window.setTimeout(() => {
        wheelDistance = 0;
      }, 180);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (["ArrowDown", "PageDown"].includes(event.key)) startTransition();
    };
    const onTouchStart = (event: TouchEvent) => {
      touchStart = event.touches[0]?.clientY ?? 0;
    };
    const onTouchEnd = (event: TouchEvent) => {
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
      if (wheelResetTimer !== null) {
        window.clearTimeout(wheelResetTimer);
      }
      if (pendingFrame.current !== null) {
        window.cancelAnimationFrame(pendingFrame.current);
      }
      if (transitionTimer.current !== null) {
        window.clearTimeout(transitionTimer.current);
      }
    };
  }, [startTransition]);

  const zoomStyle = lensGeometry
    ? ({
        "--camera-origin-x": `${lensGeometry.originX}px`,
        "--camera-origin-y": `${lensGeometry.originY}px`,
        "--camera-translate-x": `${lensGeometry.translateX}px`,
        "--camera-translate-y": `${lensGeometry.translateY}px`,
        "--camera-lens-x": `${lensGeometry.lensViewportX}px`,
        "--camera-lens-y": `${lensGeometry.lensViewportY}px`,
        "--camera-lens-size": `${lensGeometry.lensDiameter}px`,
        "--camera-overlay-scale": lensGeometry.overlayScale,
        "--camera-fill-scale": lensGeometry.overlayScale / productZoomConfig.zoomScale,
        "--camera-zoom-scale": productZoomConfig.zoomScale,
        "--camera-zoom-duration": `${productZoomConfig.durationMs}ms`,
        "--camera-destination": productZoomConfig.destinationColor,
      } satisfies CameraZoomProperties)
    : undefined;

  return (
    <div className={`landing ${zooming ? "is-zooming" : ""}`}>
      <button
        className="skip-link"
        onClick={() => document.getElementById("main-content")?.focus()}
      >
        Skip to content
      </button>

      <nav className="topbar" aria-label="Public navigation">
        <button className="enter-button" onClick={startTransition}>
          <span>Explore Optis</span>
          <span className="enter-arrow" aria-hidden="true">
            ↗
          </span>
        </button>
      </nav>

      <main id="main-content" tabIndex={-1}>
        <section className="hero" aria-labelledby="hero-title">
          <ProductIllustration
            config={productZoomConfig}
            productRef={productRef}
            imageRef={imageRef}
            lensAnchorRef={lensAnchorRef}
            onImageLoad={measureLens}
            zoomStyle={zoomStyle}
          />
          <div className="hero-copy">
            <h1 id="hero-title" className="display-title">
              Your world. <span>Within reach.</span>
            </h1>
          </div>
        </section>
      </main>

      <CameraZoomTransition active={zooming} zoomStyle={zoomStyle} />
    </div>
  );
}

function OptisAppShell({ exit }: { exit: () => void }) {
  return (
    <main className="optis-app-shell">
      <div className="app-shell-brand">OPTIS</div>
      <div className="app-ready-state">
        <span aria-hidden="true" />
        <p>Application ready</p>
      </div>
      <button onClick={exit}>Return to landing</button>
    </main>
  );
}

export default function App() {
  const [page, setPage] = useState<"landing" | "app">("landing");

  return page === "landing" ? (
    <OptisLanding enterApp={() => setPage("app")} />
  ) : (
    <OptisAppShell exit={() => setPage("landing")} />
  );
}
