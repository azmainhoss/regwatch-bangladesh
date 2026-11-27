/** Big claim on one side, a product card on the other; sides alternate; cards lift on hover. */
export default function FeatureSplits() {
  return (
    <>
      <Split eyebrow="Summaries" h="Read a circular in a minute." p="Summary, what has changed, requirements, deadlines and who it applies to, in that order, every time.">
        <div className="hx-mock hx-lift p-5">
          <div className="flex flex-wrap gap-2">
            <span className="hx-pill bg-[#c0392b] text-white">HIGH</span>
            <span className="hx-pill border border-line text-accent">✓ Ready</span>
          </div>
          <div className="hx-mono mt-4 text-[13px] font-semibold text-accent">FEPD-2 Circular Letter No. 03</div>
          <div className="mt-1 text-[18px] font-bold leading-snug text-ink">Price-verification platform and a central price-monitoring cell</div>
          <div className="hx-eyebrow mt-4" style={{ color: "rgb(var(--ink-3))" }}>What banks must do</div>
          <p className="mt-1.5 text-[15px] leading-relaxed text-ink-2">
            Set up a dedicated cell to verify trade prices, and subscribe to an international price-verification platform.{" "}
            <span className="font-semibold text-accent">Page 1</span>
          </p>
          <div className="hx-mono mt-4 flex justify-between border-t border-line pt-3 text-[13.5px] font-semibold text-ink">
            <span>Authorised dealers</span>
            <span>Due 1 Jan 2027</span>
          </div>
        </div>
      </Split>

      <Split r eyebrow="Mind map" h="See the whole circular at once." p="Every circular as a map: what changed, what to do, who must do it and by when. Tap any point to open its page.">
        <div className="hx-mock hx-lift p-6">
          <svg viewBox="0 0 440 250" className="w-full" role="img" aria-label="Mind map of a circular">
            <g fill="none" stroke="rgb(var(--line))" strokeWidth="2">
              <path d="M150 125 C 200 125, 200 45, 250 45" /><path d="M150 125 C 200 125, 200 105, 250 105" /><path d="M150 125 C 200 125, 200 165, 250 165" /><path d="M150 125 C 200 125, 200 220, 250 220" />
            </g>
            <rect x="10" y="100" width="140" height="50" rx="10" fill="#225E48" />
            <text x="80" y="122" textAnchor="middle" fill="#fff" fontSize="13" fontWeight="700">FEPD-2 CL 03</text>
            <text x="80" y="139" textAnchor="middle" fill="#cfe7dc" fontSize="11">Price verification</text>
            {[["What changed", 45, "#2563eb"], ["What banks must do", 105, "#225E48"], ["Who it applies to", 165, "#b7791f"], ["Dates", 220, "#7c3aed"]].map(([t, y, c]) => (
              <g key={t as string}>
                <rect x="250" y={(y as number) - 17} width="180" height="34" rx="17" fill="rgb(var(--surface))" stroke={c as string} strokeWidth="1.5" />
                <text x="340" y={(y as number) + 5} textAnchor="middle" fill={c as string} fontSize="13" fontWeight="600">{t as string}</text>
              </g>
            ))}
          </svg>
        </div>
      </Split>

      <Split
        eyebrow="Ask"
        h="Ask anything. Get the page."
        p="Answers come from the circulars themselves, each with the page it came from. ECL, IFRS 9 and expected credit loss mean the same thing here."
      >
        <div className="hx-mock hx-lift p-5">
          <div className="hx-eyebrow" style={{ color: "rgb(var(--ink-3))" }}>You asked</div>
          <p className="mb-4 mt-1.5 text-[16px] font-semibold text-ink">Can ADs settle cross-border payments in Taka?</p>
          <div className="hx-eyebrow" style={{ color: "rgb(var(--ink-3))" }}>Answer</div>
          <p className="mt-1.5 text-[15px] leading-relaxed text-ink-2">
            Yes, for the transactions the circular lists, following its reporting rules.{" "}
            <span className="font-semibold text-accent">FEPD-1 Circular No. 38/2026 · Page 1</span>
          </p>
        </div>
      </Split>

      <Split r eyebrow="History & links" h="Know what's still in force." p="Which circular amends, repeals or replaces which, shown on every page. No more acting on a rule that was cancelled last week.">
        <div className="hx-mock hx-lift p-6">
          {[["SDAD Circular Letter No. 22", "22 Nov 2026", "Approved downtime for a core-banking upgrade", false], ["SDAD Circular Letter No. 24", "25 Nov 2026", "Cancels Circular Letter No. 22", true]].map(([r, d, t, on], i) => (
            <div key={r as string} className="flex gap-4">
              <div className="flex flex-col items-center">
                <span className={`mt-1.5 h-3 w-3 rounded-full ${on ? "bg-accent" : "border-2 border-ink-3"}`} />
                {i === 0 && <span className="my-1 w-px flex-1 bg-line" />}
              </div>
              <div className={i === 0 ? "pb-6" : ""}>
                <div className="hx-mono text-[12.5px] text-ink-3">{d as string}</div>
                <div className={`text-[15px] font-semibold ${on ? "text-ink" : "text-ink-3 line-through"}`}>{r as string}</div>
                <div className="text-[14px] text-ink-2">{t as string}</div>
                {i === 0 && <span className="mt-1.5 inline-block rounded-md bg-[#fde8e6] px-2 py-0.5 text-[12px] font-semibold text-[#b42318]">Repealed</span>}
              </div>
            </div>
          ))}
        </div>
      </Split>
    </>
  );
}

function Split({ eyebrow, h, p, r, children }: { eyebrow: string; h: string; p: string; r?: boolean; children: React.ReactNode }) {
  return (
    <section className={`hx-screen hx-split hx-reveal ${r ? "r" : ""}`}>
      <div>
        <div className="hx-eyebrow">{eyebrow}</div>
        <h2 className="hx-h2 mt-3">{h}</h2>
        <p className="hx-lead mt-4">{p}</p>
      </div>
      <div className="hx-cardslot">{children}</div>
    </section>
  );
}
