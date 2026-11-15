import { Workspace } from "./phase2/Workspace";
import { type RefObject, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

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

// The focal point was measured from the red circular lens in the 1078 × 375 source asset.
// Future hardware only needs a new source, normalized lens point, and optional scale tuning.
const productZoomConfig: ProductZoomConfig = {
  imageSrc: "/stride-glasses.png",
  lensPoint: {
    x: 0.9309,
    y: 0.2242,
  },
  lensDiameterRatio: 0.05,
  zoomScale: 15,
  durationMs: 1200,
  destinationColor: "#102B40",
};

function Spectacles({
  config,
  productRef,
  floatRef,
  imageRef,
  lensAnchorRef,
  onImageLoad,
}: {
  config: ProductZoomConfig;
  productRef: RefObject<HTMLDivElement | null>;
  floatRef: RefObject<HTMLDivElement | null>;
  imageRef: RefObject<HTMLImageElement | null>;
  lensAnchorRef: RefObject<HTMLSpanElement | null>;
  onImageLoad: () => void;
}) {
  return (
    <div className="spectacles" ref={productRef}>
      <div className="spectacles-float" ref={floatRef}>
        <img
          ref={imageRef}
          src={config.imageSrc}
          alt=""
          aria-hidden="true"
          decoding="async"
          fetchPriority="high"
          onLoad={onImageLoad}
        />
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
  floatRef,
  imageRef,
  lensAnchorRef,
  onImageLoad,
  stageWordRef,
}: {
  config: ProductZoomConfig;
  productRef: RefObject<HTMLDivElement | null>;
  floatRef: RefObject<HTMLDivElement | null>;
  imageRef: RefObject<HTMLImageElement | null>;
  lensAnchorRef: RefObject<HTMLSpanElement | null>;
  onImageLoad: () => void;
  stageWordRef: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div className="product-illustration motion-stage">
      <div className="stage-word" ref={stageWordRef} aria-hidden="true">
        {"OPTIS".split("").map((letter, index) => (
          <span key={`${letter}-${index}`}>{letter}</span>
        ))}
      </div>
      <Spectacles
        config={config}
        productRef={productRef}
        floatRef={floatRef}
        imageRef={imageRef}
        lensAnchorRef={lensAnchorRef}
        onImageLoad={onImageLoad}
      />
    </div>
  );
}

function CameraZoomTransition({
  active,
  apertureRef,
  fillRef,
}: {
  active: boolean;
  apertureRef: RefObject<HTMLDivElement | null>;
  fillRef: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div className={`camera-zoom-transition ${active ? "is-active" : ""}`} aria-hidden="true">
      <div className="camera-dark-aperture" ref={apertureRef}>
        <div className="camera-dark-fill" ref={fillRef} />
      </div>
    </div>
  );
}

function PharosLanding({ enterApp, prepareApp }: { enterApp: () => void; prepareApp: () => void }) {
  const [zooming, setZooming] = useState(false);
  const transitionStarted = useRef(false);
  const mounted = useRef(true);
  const geometryRef = useRef<LensGeometry | null>(null);
  const landingRef = useRef<HTMLDivElement>(null);
  const productRef = useRef<HTMLDivElement>(null);
  const floatRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const lensAnchorRef = useRef<HTMLSpanElement>(null);
  const stageWordRef = useRef<HTMLDivElement>(null);
  const heroCopyRef = useRef<HTMLDivElement>(null);
  const topbarRef = useRef<HTMLElement>(null);
  const apertureRef = useRef<HTMLDivElement>(null);
  const fillRef = useRef<HTMLDivElement>(null);

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

    return geometry;
  }, []);

  const applyGeometry = useCallback((geometry: LensGeometry) => {
    const root = landingRef.current;
    if (!root) return;

    root.style.setProperty("--camera-origin-x", `${geometry.originX}px`);
    root.style.setProperty("--camera-origin-y", `${geometry.originY}px`);
    root.style.setProperty("--camera-translate-x", `${geometry.translateX}px`);
    root.style.setProperty("--camera-translate-y", `${geometry.translateY}px`);
    root.style.setProperty("--camera-lens-x", `${geometry.lensViewportX}px`);
    root.style.setProperty("--camera-lens-y", `${geometry.lensViewportY}px`);
    root.style.setProperty("--camera-lens-size", `${geometry.lensDiameter}px`);
    root.style.setProperty("--camera-destination", productZoomConfig.destinationColor);
  }, []);

  useLayoutEffect(() => {
    mounted.current = true;
    const updateGeometry = () => {
      const geometry = measureLens();
      if (geometry) {
        geometryRef.current = geometry;
        applyGeometry(geometry);
      }
    };

    const frame = window.requestAnimationFrame(updateGeometry);
    const onResize = () => {
      if (!transitionStarted.current) updateGeometry();
    };

    window.addEventListener("resize", onResize);
    return () => {
      mounted.current = false;
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", onResize);
    };
  }, [applyGeometry, measureLens]);

  useLayoutEffect(() => {
    if (!zooming || !geometryRef.current) return;

    const geometry = geometryRef.current;
    const product = productRef.current;
    const aperture = apertureRef.current;
    const fill = fillRef.current;
    if (!product || !aperture || !fill) return;

    const duration = productZoomConfig.durationMs;
    const movementEasing = "cubic-bezier(0.76, 0, 0.24, 1)";
    const fillScale = geometry.overlayScale / productZoomConfig.zoomScale;
    const movementKeyframes: Keyframe[] = [
      { transform: "translate3d(0, 0, 0) scale(1)", offset: 0 },
      { transform: "translate3d(0, 0, 0) scale(1)", offset: 0.12 },
      {
        transform: `translate3d(${geometry.translateX}px, ${geometry.translateY}px, 0) scale(${productZoomConfig.zoomScale})`,
        offset: 1,
      },
    ];

    const animations = [
      product.animate(movementKeyframes, {
        duration,
        easing: movementEasing,
        fill: "forwards",
      }),
      aperture.animate(movementKeyframes, {
        duration,
        easing: movementEasing,
        fill: "forwards",
      }),
      fill.animate(
        [
          { opacity: 0, transform: "scale(0.3)", offset: 0 },
          { opacity: 0, transform: "scale(0.3)", offset: 0.42 },
          { opacity: 0.22, transform: "scale(1)", offset: 0.6 },
          { opacity: 0.97, transform: `scale(${fillScale * 0.44})`, offset: 0.8 },
          { opacity: 1, transform: `scale(${fillScale})`, offset: 1 },
        ],
        {
          duration,
          easing: "cubic-bezier(0.32, 0, 0.1, 1)",
          fill: "forwards",
        },
      ),
      ...[stageWordRef.current, heroCopyRef.current, topbarRef.current]
        .filter((element): element is HTMLElement => element !== null)
        .map((element) =>
          element.animate([{ opacity: 1 }, { opacity: 0 }], {
            duration: 380,
            easing: "ease-out",
            fill: "forwards",
          }),
        ),
    ];

    const timelineStart = document.timeline.currentTime;
    if (timelineStart !== null) {
      animations.forEach((animation) => {
        animation.startTime = timelineStart;
      });
    }

    let cancelled = false;
    void animations[0].finished.then(() => {
      if (!cancelled && mounted.current) enterApp();
    });

    return () => {
      cancelled = true;
      animations.forEach((animation) => animation.cancel());
    };
  }, [enterApp, zooming]);

  const startTransition = useCallback(async () => {
    if (transitionStarted.current) return;
    transitionStarted.current = true;

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      enterApp();
      return;
    }

    const image = imageRef.current;
    const floatingProduct = floatRef.current;
    if (!image || !floatingProduct) {
      enterApp();
      return;
    }

    try {
      await image.decode();
    } catch {
      if (!image.complete || image.naturalWidth === 0) {
        enterApp();
        return;
      }
    }

    await new Promise<void>((resolve) => {
      window.requestAnimationFrame(() => window.requestAnimationFrame(() => resolve()));
    });
    if (!mounted.current) return;

    const frozenFloatTransform = window.getComputedStyle(floatingProduct).transform;
    floatingProduct.style.animation = "none";
    floatingProduct.style.transform =
      frozenFloatTransform === "none" ? "translate3d(0, 0, 0)" : frozenFloatTransform;

    const geometry = measureLens();
    if (!geometry) {
      enterApp();
      return;
    }

    geometryRef.current = geometry;
    applyGeometry(geometry);
    prepareApp();
    setZooming(true);
  }, [applyGeometry, enterApp, measureLens, prepareApp]);

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
    };
  }, [startTransition]);

  return (
    <div ref={landingRef} className={`landing ${zooming ? "is-zooming" : ""}`}>
      <button
        className="skip-link"
        onClick={() => document.getElementById("main-content")?.focus()}
      >
        Skip to content
      </button>

      <nav className="topbar" ref={topbarRef} aria-label="Public navigation">
        <button className="enter-button" onClick={startTransition}>
          <span>Explore OPTIS</span>
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
            floatRef={floatRef}
            imageRef={imageRef}
            lensAnchorRef={lensAnchorRef}
            onImageLoad={() => {
              const geometry = measureLens();
              if (geometry) {
                geometryRef.current = geometry;
                applyGeometry(geometry);
              }
            }}
            stageWordRef={stageWordRef}
          />
          <div className="hero-copy" ref={heroCopyRef}>
            <h1 id="hero-title" className="display-title">
              Your world. <span>Within reach.</span>
            </h1>
          </div>
        </section>
      </main>

      <CameraZoomTransition active={zooming} apertureRef={apertureRef} fillRef={fillRef} />
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState<"landing" | "transitioning" | "app">("landing");
  const enterApp = useCallback(() => setPage("app"), []);
  const prepareApp = useCallback(() => setPage("transitioning"), []);
  const exitApp = useCallback(() => setPage("landing"), []);

  return (
    <div className="experience-root">
      <div
        className={`app-shell-layer ${
          page === "app" ? "is-visible" : page === "transitioning" ? "is-staged" : "is-preloaded"
        }`}
        aria-hidden={page !== "app"}
        inert={page !== "app"}
      >
        <Workspace exit={exitApp} active={page === "app"} />
      </div>
      {page !== "app" && <PharosLanding enterApp={enterApp} prepareApp={prepareApp} />}
    </div>
  );
}
