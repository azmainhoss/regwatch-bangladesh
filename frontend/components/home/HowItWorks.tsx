"use client";

import { useEffect, useRef, useState } from "react";

/** Five numbered steps that play one after another (6 s each, with a progress line); hover or tap jumps to a step.
 *  The frame on the right swaps to a small picture of that step. */

const STEPS = [
  {
    n: "01. Caught",
    h: "The day it's issued.",
    p: "We check Bangladesh Bank's website every hour. A new circular is on your dashboard, and in your evening email, the same day.",
    title: "Caught the day it's issued",
    tags: ["Hourly checks", "Same day", "Evening email"],
  },
  {
    n: "02. Explained",
    h: "What changed, in plain English.",
    p: "A short summary, what has changed and what banks must do. Bangla circulars are explained in English, with the Bangla original one tap away.",
    title: "Explained in plain English",
    tags: ["Summary", "What changed", "Requirements", "Bangla original"],
  },
  {
    n: "03. Proven",
    h: "Every point shows its page.",
    p: "Each point links to the exact page and lines of the original. Points are checked against the circular's text before they're marked Ready.",
    title: "Every point shows its page",
    tags: ["Page links", "Checked against the text", "Ready"],
  },
  {
    n: "04. For you",
    h: "Says who it applies to.",
    p: "Authorised dealers, NBFIs, Islamic banks… Tell us your institution type once and every circular is flagged for you, or not.",
    title: "Says who it applies to",
    tags: ["AD banks", "Islamic banks", "NBFIs", "MFS", "Importers"],
  },
  {
    n: "05. Done",
    h: "Assigned, tracked, signed off.",
    p: "Turn a requirement into a task with an owner and a due date, attach evidence and sign off. Your audit trail builds itself.",
    title: "Assigned, tracked, signed off",
    tags: ["Registers", "Tasks", "Evidence", "Audit trail"],
  },
];

export default function HowItWorks() {
  const [cur, setCur] = useState(0);
  const [run, setRun] = useState(0); // restarts the progress line
  const t = useRef<number>();
  const box = useRef<HTMLElement>(null);
  // Steps start playing only once the section is on screen (owner, 2026-11-28).
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && (setSeen(true), setRun((r) => r + 1), io.disconnect()), { threshold: 0.15 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  useEffect(() => {
    window.clearTimeout(t.current);
    if (!seen) return;
    t.current = window.setTimeout(() => go((cur + 1) % STEPS.length), 6000);
    return () => window.clearTimeout(t.current);
  }, [cur, run, seen]);
  const go = (i: number) => {
    setCur(i);
    setRun((r) => r + 1);
  };

  return (
    <section ref={box} aria-labelledby="hx-how-h" className="flex flex-col gap-10">
      <h2 id="hx-how-h" className="hx-h2 text-center">
        From Bangladesh Bank&apos;s PDF
        <br />
        to your team&apos;s evidence.
      </h2>
      <div className="hx-steps">
        <div>
          {STEPS.map((s, i) => (
            <button key={s.n} type="button" className={`hx-step ${i === cur ? "on" : ""}`} onMouseEnter={() => i !== cur && go(i)} onClick={() => go(i)} aria-expanded={i === cur}>
              <div className="n">{s.n}</div>
              <h3>{s.h}</h3>
              <p>{s.p}</p>
              <span key={i === cur ? run : -1} className="bar" style={seen ? undefined : { animation: "none" }} />
            </button>
          ))}
        </div>
        <div className="hx-stagebox">
          <div className="text-center text-[15px] font-semibold text-ink">{STEPS[cur].title}</div>
          <div className="hx-frame">
            <svg className="c" style={{ top: 10, left: 10 }} viewBox="0 0 14 14"><path d="M0 7V0h7" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
            <svg className="c" style={{ bottom: 10, right: 10 }} viewBox="0 0 14 14"><path d="M14 7v7H7" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
            <div key={cur} className="hx-scene">
              <Scene i={cur} />
            </div>
          </div>
          <div className="hx-tags">
            {STEPS[cur].tags.map((x) => <span key={x}>{x}</span>)}
          </div>
        </div>
      </div>
    </section>
  );
}

function Scene({ i }: { i: number }) {
  if (i === 0)
    return (
      <div className="flex items-center justify-between gap-3">
        <div className="hx-mock w-[38%] text-center">
          <div className="hx-mono text-[11px] text-ink-3">bb.org.bd</div>
          <div className="mt-2 space-y-1.5"><div className="hx-line" /><div className="hx-line w-4/5" /><div className="hx-line w-3/5" /></div>
          <div className="mt-2 text-[12px] font-semibold text-ink">New PDF</div>
        </div>
        <svg width="60" height="20" viewBox="0 0 60 20" className="text-accent"><path d="M2 10h50" stroke="currentColor" strokeWidth="2" strokeDasharray="4 4"><animate attributeName="stroke-dashoffset" from="16" to="0" dur=".8s" repeatCount="indefinite" /></path><path d="M50 4l8 6-8 6" fill="none" stroke="currentColor" strokeWidth="2" /></svg>
        <div className="hx-mock w-[46%]">
          <div className="flex items-center justify-between"><span className="text-[12px] font-semibold text-accent">Today</span><span className="rounded-full bg-accent px-2 text-[11px] font-bold text-accent-ink">New</span></div>
          <div className="mt-2 text-[13px] font-semibold leading-snug text-ink">FEPD-2 Circular Letter No. 03</div>
          <div className="mt-2 border-t border-line pt-2 text-[11.5px] text-ink-3">✉ In your 7:30 pm email</div>
        </div>
      </div>
    );
  if (i === 1)
    return (
      <div className="hx-mock">
        <div className="hx-eyebrow">Summary</div>
        <p className="mt-1 text-[13.5px] leading-snug text-ink-2">Authorised dealers must set up a price-monitoring cell and subscribe to a price-verification platform.</p>
        <div className="hx-eyebrow mt-3">What has changed</div>
        <p className="mt-1 text-[13.5px] leading-snug text-ink-2">New requirement, in force from 1 January 2027.</p>
        <div className="hx-eyebrow mt-3">What banks must do</div>
        <div className="mt-1.5 space-y-1.5"><div className="hx-line" /><div className="hx-line w-4/5" /></div>
        <div className="mt-3 inline-block rounded-md border border-line px-2 py-1 font-bangla text-[12px] text-ink-2">বাংলা মূল কপি</div>
      </div>
    );
  if (i === 2)
    return (
      <div className="relative">
        <div className="hx-mock w-[80%]">
          <div className="text-[13.5px] font-semibold text-ink">Subscribe to a price-verification platform</div>
          <span className="mt-2 inline-flex items-center gap-1 rounded-md bg-accent-soft px-2 py-0.5 text-[12px] font-semibold text-accent">Page 1 · ✓ Ready</span>
        </div>
        <div className="hx-mock -mt-3 ml-auto w-[78%] pt-6">
          <div className="hx-mono text-[10.5px] text-ink-3">Original PDF · page 1</div>
          <div className="mt-2 space-y-1.5"><div className="hx-line" /><div className="hx-line w-11/12" /></div>
          <div className="my-2 rounded bg-[#f9e39b] px-1.5 py-1 text-[11.5px] leading-snug text-[#3d3200]">ADs are also advised to … subscribe to at least one internationally recognized price verification platform…</div>
          <div className="hx-line w-3/4" />
        </div>
      </div>
    );
  if (i === 3)
    return (
      <div className="space-y-2.5">
        {[["AD bank", "For you", true], ["Islamic bank", "For you", true], ["NBFI", "Not for you", false], ["MFS", "Not for you", false]].map(([k, v, on]) => (
          <div key={k as string} className="hx-mock flex items-center justify-between py-2.5">
            <span className="text-[14px] font-semibold text-ink">{k}</span>
            <span className={`rounded-full px-2.5 py-0.5 text-[12px] font-bold ${on ? "bg-[#2563eb] text-white" : "bg-sunken text-ink-3"}`}>{v}</span>
          </div>
        ))}
      </div>
    );
  return (
    <div className="hx-mock">
      <div className="flex items-center justify-between"><span className="text-[13.5px] font-semibold text-ink">Set up price-monitoring cell</span><span className="rounded-md bg-ok-soft px-2 py-0.5 text-[11.5px] font-bold text-ok">Signed off</span></div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[12px]">
        <div><div className="text-ink-3">Owner</div><div className="font-semibold text-ink">Head of Trade Services</div></div>
        <div><div className="text-ink-3">Due</div><div className="hx-mono font-semibold text-ink">31 Dec 2026</div></div>
      </div>
      <div className="mt-3 rounded-md border border-dashed border-line px-2.5 py-2 text-[12px] text-ink-2">📎 Platform subscription.pdf</div>
      <div className="mt-2 text-[11.5px] text-ink-3">Recorded in the audit trail</div>
    </div>
  );
}
