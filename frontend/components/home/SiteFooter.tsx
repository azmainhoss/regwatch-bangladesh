"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import "./home.css";

/** Dark site footer: link columns, the disclaimer, and a giant dotted "Amar Circular" that lights up under the mouse. */
export default function SiteFooter({ links }: { links: [string, string][] }) {
  return (
    <footer className="hx-foot pb-[calc(80px+env(safe-area-inset-bottom))] sm:pb-0">
      <div className="mx-auto max-w-[1480px] px-4 pt-14 sm:px-6 lg:px-8">
        <div className="grid gap-10 border-b border-white/10 pb-10 md:grid-cols-[1.4fr_2fr_1fr]">
          <div>
            <div className="flex items-center gap-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/brand/lockup-dark.svg" alt="Amar Circular" width={150} height={50} className="h-[50px] w-auto" />
            </div>
            <p className="mt-4 max-w-[340px] text-[15px] leading-relaxed text-[#a9bdb4]">Every Bangladesh Bank circular, explained the day it&apos;s issued, with the page each point comes from.</p>
          </div>
          <div>
            <h5 className="mb-3 text-[14px] font-semibold text-white">Circulars</h5>
            <nav aria-label="Circular lists" className="grid grid-cols-2 gap-x-6 gap-y-2 text-[14.5px] sm:grid-cols-3">
              {links.map(([href, label]) => (
                <Link key={href} href={href}>{label}</Link>
              ))}
            </nav>
          </div>
          <div>
            <h5 className="mb-3 text-[14px] font-semibold text-white">Product</h5>
            <nav className="grid gap-2 text-[14.5px]">
              <Link href="/dashboard">Dashboard</Link>
              <Link href="/search">Search &amp; Ask</Link>
              <Link href="/plans">Plans</Link>
            </nav>
          </div>
        </div>
        <div className="flex flex-col gap-1 py-5 text-[13px] text-[#6f8178] sm:flex-row sm:justify-between">
          <span>This is not an official reference. Please verify the original reference at your own responsibility before making any decision.</span>
          <span className="shrink-0">Source: Bangladesh Bank circulars</span>
        </div>
      </div>
      <DotWord />
    </footer>
  );
}

function DotWord() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const cx = cv.getContext("2d")!;
    let pts: [number, number, number][] = [];
    let mx = -999;
    let my = -999;
    let lit = 0; // fades the glow in and out
    let raf = 0;
    const draw = () => {
      const r = window.devicePixelRatio || 1;
      cx.setTransform(r, 0, 0, r, 0, 0);
      cx.clearRect(0, 0, cv.width, cv.height);
      for (const [x, y, s] of pts) {
        const k = Math.max(0, 1 - Math.hypot(x - mx, y - my) / 150) * lit;
        cx.fillStyle = `rgba(${(95 + 110 * k) | 0},${(170 + 70 * k) | 0},${(135 + 60 * k) | 0},${0.2 + 0.75 * k})`;
        cx.beginPath();
        cx.arc(x, y, s * 0.3 + k * 1.7, 0, 7);
        cx.fill();
      }
    };
    const build = () => {
      const W = cv.clientWidth;
      const H = Math.round(W * 0.17);
      if (W < 10 || H < 2) return; // not laid out yet (hidden page, first paint)
      const r = window.devicePixelRatio || 1;
      cv.width = W * r;
      cv.height = H * r;
      cv.style.height = `${H}px`;
      const o = document.createElement("canvas");
      o.width = W;
      o.height = H;
      const c = o.getContext("2d")!;
      const txt = "Amar Circular";
      c.font = `600 ${H}px Georgia, serif`;
      const size = (H * W * 0.98) / c.measureText(txt).width;
      c.font = `600 ${Math.min(size, H * 1.05)}px Georgia, serif`;
      c.fillText(txt, W * 0.01, H * 0.86);
      const d = c.getImageData(0, 0, W, H).data;
      const step = Math.max(6, Math.round(W / 175));
      pts = [];
      for (let y = 0; y < H; y += step) for (let x = 0; x < W; x += step) if (d[(y * W + x) * 4 + 3] > 128) pts.push([x, y, step]);
      draw();
    };
    const fade = (to: number) => {
      cancelAnimationFrame(raf);
      const tick = () => {
        lit += (to - lit) * 0.15;
        draw();
        if (Math.abs(to - lit) > 0.01) raf = requestAnimationFrame(tick);
      };
      tick();
    };
    const move = (e: PointerEvent) => {
      const b = cv.getBoundingClientRect();
      mx = e.clientX - b.left;
      my = e.clientY - b.top;
      if (lit < 0.99) fade(1);
      else draw();
    };
    const leave = () => fade(0);
    build();
    cv.addEventListener("pointermove", move);
    cv.addEventListener("pointerleave", leave);
    window.addEventListener("resize", build);
    return () => {
      cancelAnimationFrame(raf);
      cv.removeEventListener("pointermove", move);
      cv.removeEventListener("pointerleave", leave);
      window.removeEventListener("resize", build);
    };
  }, []);
  return <canvas ref={ref} className="hx-word" aria-hidden />;
}
