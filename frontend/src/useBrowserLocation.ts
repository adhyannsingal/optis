import { useEffect, useRef, useState } from "react";

export function useBrowserLocation(token: string) {
  const [sharing, setSharing] = useState(false);
  const [locationMessage, setLocationMessage] = useState("");
  const stopWatch = useRef<(() => void) | null>(null);

  useEffect(() => {
    setSharing(false);
    setLocationMessage("");
    return () => stopWatch.current?.();
  }, [token]);

  function stop(message = "Location sharing stopped.") {
    stopWatch.current?.();
    setSharing(false);
    setLocationMessage(message);
  }

  function start() {
    if (!token || stopWatch.current) return;
    if (!window.isSecureContext || !navigator.geolocation) {
      setLocationMessage("Open Optis over HTTPS to use this device’s location.");
      return;
    }

    setSharing(true);
    setLocationMessage("Waiting for a location fix…");
    let sending = false;
    let stopped = false;
    let lastTimestamp = 0;
    const controller = new AbortController();

    const pauseOnHide = () => {
      if (document.hidden) stop("Location sharing paused. Tap Use my location when you return.");
    };

    const watch = navigator.geolocation.watchPosition(async position => {
      const age = Date.now() - position.timestamp;
      if (stopped || sending || position.timestamp <= lastTimestamp || age < 0 || age > 5000) return;
      sending = true;
      try {
        const response = await fetch("/v1/location", {
          method: "POST",
          headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(2500)]),
          cache: "no-store",
          body: JSON.stringify({
            seq: Math.trunc(position.timestamp),
            lat_deg: position.coords.latitude,
            lon_deg: position.coords.longitude,
            horizontal_accuracy_m: position.coords.accuracy,
            fix_time_utc: new Date(position.timestamp).toISOString(),
            age_at_send_ms: Math.trunc(age),
          }),
        });
        if (stopped) return;
        if (!response.ok) {
          const result = await response.json();
          if (!stopped) setLocationMessage(typeof result.detail === "string" ? result.detail : "Optis rejected the location fix.");
          return;
        }
        lastTimestamp = position.timestamp;
        setLocationMessage("Sharing this device’s location.");
      } catch {
        if (!stopped) setLocationMessage("Can’t send location to Optis. Check the connection.");
      } finally {
        sending = false;
      }
    }, error => {
      if (stopped) return;
      if (error.code === error.PERMISSION_DENIED) {
        stop("Location access was denied. Allow it in Safari’s website settings, then try again.");
      } else {
        setLocationMessage("Waiting for location. Try stepping outdoors.");
      }
    }, { enableHighAccuracy: true, maximumAge: 0, timeout: 10000 });

    stopWatch.current = () => {
      stopped = true;
      navigator.geolocation.clearWatch(watch);
      document.removeEventListener("visibilitychange", pauseOnHide);
      controller.abort();
      stopWatch.current = null;
    };
    document.addEventListener("visibilitychange", pauseOnHide);
  }

  return { sharing, locationMessage, start, stop };
}
