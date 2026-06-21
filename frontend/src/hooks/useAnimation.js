import { useEffect, useState } from "react";

/**
 * Returns a value in [0, 1] that completes one full cycle every `periodMs`.
 * Throttled to ~10 fps, paused when the document is hidden, and — crucially —
 * completely idle when `active` is false so a static map costs zero renders.
 */
export function useAnimatedT(periodMs = 4000, fps = 10, active = true) {
  const [t, setT] = useState(0);
  useEffect(() => {
    if (!active) return undefined; // no ticking, no re-renders when idle
    let raf;
    let last = performance.now();
    const start = last;
    const frame = 1000 / fps;

    const tick = (now) => {
      if (document.hidden) {
        raf = requestAnimationFrame(tick);
        return;
      }
      if (now - last >= frame) {
        const elapsed = (now - start) % periodMs;
        setT(elapsed / periodMs);
        last = now;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [periodMs, fps, active]);
  return active ? t : 0;
}

/** Counter starting at `from` ramping to `to` over `durationMs`. */
export function useCounter(to, durationMs = 800) {
  const [v, setV] = useState(0);
  useEffect(() => {
    let raf;
    const start = performance.now();
    const from = 0;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setV(from + (to - from) * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [to, durationMs]);
  return v;
}
