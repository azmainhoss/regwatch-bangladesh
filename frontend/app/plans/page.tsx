"use client";

import { useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { getStoredUser } from "@/services/api";
import { requestUpgrade, usePlan, type PlanInfo } from "@/services/planStore";
import AccountModal from "@/components/AccountModal";
import { Notice, SkeletonLine } from "@/components/ui";

const taka = (n: number) => `৳${n.toLocaleString("en-US")}`;

const RANK: Record<string, number> = { FREE: 0, PRO: 1, ENTERPRISE: 2 };

function PlanCard({ p, current, below, pending, onPick }: { p: PlanInfo; current: boolean; below: boolean; pending: boolean; onPick: () => void }) {
  const featured = p.code === "PRO";
  return (
    <div className={`flex flex-col rounded-panel border bg-surface p-5 ${featured ? "border-accent shadow-panel" : "border-line"}`}>
      <div className="flex items-center justify-between">
        <h2 className="text-[19px] font-semibold text-ink">{p.name}</h2>
        {current && <span className="rounded-full bg-accent-soft px-2.5 py-0.5 text-[12px] font-semibold text-accent">Your plan</span>}
        {!current && pending && <span className="rounded-full bg-warn-soft px-2.5 py-0.5 text-[12px] font-semibold text-warn">Requested</span>}
      </div>
      <p className="mt-2 text-ink">
        {p.price_bdt_month === 0 ? (
          <span className="text-[30px] font-semibold tracking-tight">Free</span>
        ) : (
          <>
            <span className="text-[30px] font-semibold tracking-tight tabular-nums">{taka(p.price_bdt_month)}</span>
            <span className="text-[14px] text-ink-3"> / {p.per} / month</span>
          </>
        )}
      </p>
      {p.min_seats > 1 && (
        <p className="mt-0.5 text-[13px] text-ink-3">
          From {p.min_seats} seats ({taka(p.price_bdt_month * p.min_seats)} a month)
        </p>
      )}
      <ul className="mt-4 flex-1 space-y-2">
        {p.features.map((f) => (
          <li key={f} className="flex gap-2 text-[14.5px] text-ink-2">
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-accent" strokeWidth={2.2} />
            {f}
          </li>
        ))}
      </ul>
      {p.code !== "FREE" && !current && !below && (
        <button type="button" onClick={onPick} disabled={pending} className={`mt-5 ${featured ? "btn-primary" : "btn-secondary"} w-full`}>
          {pending ? "Request sent" : p.code === "ENTERPRISE" ? "Talk to us" : "Move to Pro"}
        </button>
      )}
    </div>
  );
}

export default function PlansPage() {
  const { me, plans } = usePlan();
  const [accountOpen, setAccountOpen] = useState(false);
  const [picked, setPicked] = useState<"PRO" | "ENTERPRISE" | null>(null);
  const [seats, setSeats] = useState(20);
  const [org, setOrg] = useState("");
  const [phone, setPhone] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  const pick = (code: string) => {
    if (!getStoredUser()) return setAccountOpen(true);
    setMsg(null);
    setPicked(code as "PRO" | "ENTERPRISE");
  };

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!picked || busy) return;
    setBusy(true);
    try {
      await requestUpgrade({ plan: picked, seats: picked === "ENTERPRISE" ? seats : 1, organization_name: org || undefined, contact_phone: phone || undefined, note: note || undefined });
      setMsg({ kind: "success", text: "Request sent. We will call you to set up payment; your plan switches on as soon as it is confirmed." });
      setPicked(null);
    } catch (err: any) {
      setMsg({ kind: "error", text: err?.message || "Could not send the request." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <AccountModal isOpen={accountOpen} onClose={() => setAccountOpen(false)} currentUser={getStoredUser()} onUserChange={() => undefined} />
      <div>
        <h1 className="text-[26px] font-semibold tracking-[-0.015em] text-ink">Plans</h1>
        <p className="mt-0.5 text-[14.5px] text-ink-3">
          {me
            ? `You are on ${me.name}${me.via_organization ? " through your bank" : ""}.${me.questions_per_day ? ` Questions today: ${me.questions_today} of ${me.questions_per_day}.` : ""}`
            : "Start free. Move up when you need more."}
        </p>
      </div>

      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}

      {plans.length === 0 ? (
        <div className="grid gap-4 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="space-y-3 rounded-panel border border-line bg-surface p-5">
              <SkeletonLine className="h-5 w-24" />
              <SkeletonLine className="h-8 w-32" />
              <SkeletonLine className="h-3 w-full" />
              <SkeletonLine className="h-3 w-3/4" />
            </div>
          ))}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          {plans.map((p) => (
            <PlanCard key={p.code} p={p} current={(me?.plan ?? "FREE") === p.code} below={RANK[p.code] < RANK[me?.plan ?? "FREE"]} pending={me?.pending_request === p.code} onPick={() => pick(p.code)} />
          ))}
        </div>
      )}

      {picked && (
        <form onSubmit={send} className="max-w-xl space-y-3 rounded-panel border border-line bg-surface p-5">
          <h2 className="text-[17px] font-semibold text-ink">{picked === "ENTERPRISE" ? "Enterprise for your bank" : "Move to Pro"}</h2>
          {picked === "ENTERPRISE" && (
            <>
              <div>
                <label className="field-label" htmlFor="plan-org">
                  Bank or company name
                </label>
                <input id="plan-org" className="field" value={org} onChange={(e) => setOrg(e.target.value)} required />
              </div>
              <div>
                <label className="field-label" htmlFor="plan-seats">
                  Seats (at least 20)
                </label>
                <input id="plan-seats" type="number" min={20} className="field" value={seats} onChange={(e) => setSeats(Math.max(1, Number(e.target.value) || 0))} />
              </div>
            </>
          )}
          <div>
            <label className="field-label" htmlFor="plan-phone">
              Phone (we call to set up payment)
            </label>
            <input id="plan-phone" className="field" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+880" />
          </div>
          <div>
            <label className="field-label" htmlFor="plan-note">
              Anything we should know (optional)
            </label>
            <textarea id="plan-note" className="field min-h-[72px]" value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-ghost" onClick={() => setPicked(null)}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={busy || (picked === "ENTERPRISE" && (seats < 20 || !org.trim()))}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Send request"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
