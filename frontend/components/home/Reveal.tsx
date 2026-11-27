"use client";

import { useEffect } from "react";

/** Fades in every .hx-reveal block as it scrolls into view. */
export default function Reveal() {
  useEffect(() => {
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => e.isIntersecting && (e.target.classList.add("hx-in"), io.unobserve(e.target))),
      { threshold: 0.12 },
    );
    document.querySelectorAll(".hx-reveal").forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
  return null;
}
