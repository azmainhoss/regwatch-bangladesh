"use client";
/** A small tooltip that shows on hover and on tap (phones), floats above the page so no list edge cuts it off,
 * and stays inside the screen. Tapping it never opens the row it sits in. */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export default function Tip({ text, children, width = 220 }: { text: string; children: React.ReactNode; width?: number }) {
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const ref = useRef<HTMLSpanElement>(null);

  const show = () => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    const left = Math.min(Math.max(8, r.left + r.width / 2 - width / 2), window.innerWidth - width - 8);
    const below = r.bottom + 6;
    setPos({ left, top: below + 70 > window.innerHeight ? Math.max(8, r.top - 66) : below });
  };

  useEffect(() => {
    if (!pos) return;
    const close = (e: MouseEvent | TouchEvent) => {
      if (!ref.current?.contains(e.target as Node)) setPos(null);
    };
    const away = () => setPos(null);
    document.addEventListener("mousedown", close);
    document.addEventListener("touchstart", close);
    window.addEventListener("scroll", away, true);
    window.addEventListener("resize", away);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("touchstart", close);
      window.removeEventListener("scroll", away, true);
      window.removeEventListener("resize", away);
    };
  }, [pos]);

  return (
    <span
      ref={ref}
      className="inline-flex"
      onMouseEnter={show}
      onMouseLeave={() => setPos(null)}
      onClick={(e) => {
        e.stopPropagation();
        e.preventDefault();
        show();
      }}
    >
      {children}
      {pos &&
        createPortal(
          <span
            role="tooltip"
            style={{ left: pos.left, top: pos.top, width }}
            className="pointer-events-none fixed z-[80] block rounded-[8px] border border-line-strong bg-surface px-2.5 py-1.5 text-left text-[12.5px] font-normal leading-snug text-ink shadow-lg"
          >
            {text}
          </span>,
          document.body,
        )}
    </span>
  );
}
