"use client";

import { useEffect, useRef } from "react";

/** Subtle dotted field behind the hero, full width. Dots near the mouse grow and turn brand green. */
export default function HeroDots({ night = false }: { night?: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const cx = cv.getContext("2d")!;
    const GAP = night ? 16 : 22;
    let W = 0;
    let H = 0;
    let mx = -9999;
    let my = -9999;
    let tx = -9999;
    let ty = -9999;
    let raf = 0;
    const dark = () => document.documentElement.classList.contains("dark");
    const draw = () => {
      const r = window.devicePixelRatio || 1;
      cx.setTransform(r, 0, 0, r, 0, 0);
      cx.clearRect(0, 0, W, H);
      const base = night ? [140, 220, 180] : dark() ? [134, 146, 141] : [150, 165, 158];
      const glow = night ? [120, 255, 190] : dark() ? [104, 194, 155] : [34, 94, 72];
      for (let y = GAP / 2; y < H; y += GAP) {
        for (let x = GAP / 2; x < W; x += GAP) {
          // Fade the field out toward the lower left, where the text sits.
          const fade = night ? Math.max(0, Math.min(1, (x / W - 0.35) * 2.4)) : Math.min(1, 0.25 + (x / W) * 0.9) * Math.min(1, 1.15 - y / H);
          const k = Math.max(0, 1 - Math.hypot(x - mx, y - my) / 170);
          const c = base.map((b, i) => Math.round(b + (glow[i] - b) * k));
          cx.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${(0.28 * fade + 0.6 * k).toFixed(3)})`;
          cx.beginPath();
          cx.arc(x, y, (night ? 1 : 1.1) + k * 2.2, 0, 7);
          cx.fill();
        }
      }
    };
    const size = () => {
      const b = cv.getBoundingClientRect();
      W = b.width;
      H = b.height;
      const r = window.devicePixelRatio || 1;
      cv.width = Math.max(1, W * r);
      cv.height = Math.max(1, H * r);
      draw();
    };
    // Ease the glow toward the pointer so it trails smoothly.
    const tick = () => {
      mx += (tx - mx) * 0.18;
      my += (ty - my) * 0.18;
      draw();
      if (Math.abs(tx - mx) > 0.5 || Math.abs(ty - my) > 0.5) raf = requestAnimationFrame(tick);
      else raf = 0;
    };
    const move = (e: PointerEvent) => {
      const b = cv.getBoundingClientRect();
      const inside = e.clientX >= b.left && e.clientX <= b.right && e.clientY >= b.top && e.clientY <= b.bottom;
      tx = inside ? e.clientX - b.left : -9999;
      ty = inside ? e.clientY - b.top : -9999;
      if (mx < -5000 && inside) { mx = tx; my = ty; }
      if (!raf) raf = requestAnimationFrame(tick);
    };
    size();
    const ro = new ResizeObserver(size);
    ro.observe(cv);
    window.addEventListener("pointermove", move, { passive: true });
    const mo = new MutationObserver(draw);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      mo.disconnect();
      window.removeEventListener("pointermove", move);
    };
  }, [night]);
  return (
    <canvas
      ref={ref}
      aria-hidden
      className={night ? "pointer-events-none absolute inset-0 h-full w-full" : "pointer-events-none absolute inset-y-0 left-1/2 -z-0 h-full w-screen -translate-x-1/2"}
    />
  );
}
