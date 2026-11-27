import Link from "next/link";
import HeroDots from "./HeroDots";

/** Dark band for compliance teams: deep green-black, dotted glow, cards that glow on hover. */
export default function TeamBand() {
  const cards = [
    ["Registers & tasks", "Turn requirements into tasks with an owner, a department and a due date."],
    ["Evidence & sign-off", "Attach proof, review it, sign it off. Every step is recorded."],
    ["Reports for the board", "What came this month, what's done, what's overdue, on one page."],
  ];
  return (
    <section className="hx-night px-6 py-16 sm:px-12 sm:py-20" aria-labelledby="hx-team-h">
      <HeroDots night />
      <div className="relative grid items-center gap-12 lg:grid-cols-2">
        <div>
          <div className="hx-eyebrow">For compliance teams</div>
          <h2 id="hx-team-h" className="hx-h2 mt-4">
            Every circular.
            <br />
            One shared register.
          </h2>
          <p className="hx-lead mt-4">
            Your whole team works from the same library: assign requirements to departments, track deadlines, attach evidence and sign off,
            with a record an inspector can follow.
          </p>
          <ul className="mt-10 grid gap-3.5 text-[18px]">
            <li className="flex items-center gap-3"><span className="hx-ring" style={{ borderColor: "#4fb6ff" }} />One library</li>
            <li className="flex items-center gap-3"><span className="hx-ring" style={{ borderColor: "#ff7b6b", animationDirection: "reverse" }} />One register for your institution</li>
            <li className="flex items-center gap-3"><span className="hx-ring" style={{ borderColor: "#d4e45a" }} />One audit trail</li>
          </ul>
        </div>
        <div className="grid gap-4">
          {cards.map(([h, p]) => (
            <Link key={h} href="/dashboard" className="hx-gc">
              <h4>{h}</h4>
              <p>{p}</p>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
