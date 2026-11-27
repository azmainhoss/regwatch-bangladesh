"use client";
/** "For you" (owner, 2026-11-28): the institution type picker, the For you pill with its reason (hover, or tap on
 * phones), the circular page line with Applies to me / Not for me, the dashboard card, and the Account section. */
import { useEffect, useRef, useState } from "react";
import { Check, X } from "lucide-react";
import {
  AudienceMe,
  Flag,
  InstitutionKind,
  markCircular,
  muteInterest,
  saveInstitution,
  useAudienceMe,
  useFlags,
} from "@/services/audienceApi";
import { getStoredUser } from "@/services/api";

const chip = (on: boolean) =>
  `rounded-full border px-3 py-1.5 text-[13px] font-semibold transition-colors ${
    on ? "border-accent bg-accent-soft text-accent" : "border-line bg-surface text-ink-2 hover:border-line-strong hover:text-ink"
  }`;

/** Institution type chips, plus "Do you have AD branches?" for banks. */
export function InstitutionPicker({
  kinds,
  kind,
  hasAd,
  onChange,
}: {
  kinds: InstitutionKind[];
  kind: string | null;
  hasAd: boolean | null;
  onChange: (kind: string, hasAd: boolean | null) => void;
}) {
  const bank = kinds.find((k) => k.code === kind)?.bank;
  return (
    <div>
      <p className="text-[13.5px] font-semibold text-ink">Your institution type</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {kinds.map((k) => (
          <button key={k.code} type="button" aria-pressed={kind === k.code} onClick={() => onChange(k.code, k.bank ? hasAd ?? true : null)} className={chip(kind === k.code)}>
            {k.label}
          </button>
        ))}
      </div>
      {bank && (
        <>
          <p className="mt-3 text-[13.5px] font-semibold text-ink">Do you have AD (foreign exchange) branches?</p>
          <div className="mt-2 flex gap-1.5">
            {[true, false].map((v) => (
              <button key={String(v)} type="button" aria-pressed={hasAd === v} onClick={() => onChange(kind!, v)} className={chip(hasAd === v)}>
                {v ? "Yes" : "No"}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/** The small "For you" pill. Hover (or tap) shows why, with "Not for me". */
export function ForYouPill({ documentId, flag }: { documentId: string; flag?: Flag }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | TouchEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("touchstart", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("touchstart", close);
    };
  }, [open]);
  if (!flag?.for_you) return null;
  const notForMe = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      await markCircular(documentId, flag.mark > 0 ? 0 : -1);
      setOpen(false);
    } finally {
      setBusy(false);
    }
  };
  return (
    <span
      ref={ref}
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onClick={(e) => {
        e.stopPropagation();
        e.preventDefault();
        setOpen(true); // hover may have opened it already; a tap elsewhere closes it
      }}
    >
      <span className="cursor-default rounded-full bg-accent-soft px-2 py-0.5 text-[11.5px] font-bold text-accent">For you</span>
      {open && (
        <span
          role="tooltip"
          className="absolute right-0 top-full z-30 mt-1.5 w-64 rounded-[10px] border border-line-strong bg-surface p-3 text-left shadow-lg"
        >
          <span className="block text-[13px] font-normal leading-snug text-ink">{flag.reason || "Applies to your institution."}</span>
          {/* A span, not a button: the pill can sit inside a list row that is itself a button. */}
          <span
            role="button"
            tabIndex={0}
            aria-disabled={busy}
            onClick={notForMe}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && notForMe(e as unknown as React.MouseEvent)}
            className="btn-secondary mt-2 inline-flex h-8 cursor-pointer px-3 text-[12.5px]"
          >
            {flag.mark > 0 ? "Undo" : "Not for me"}
          </span>
        </span>
      )}
    </span>
  );
}

/** One "For you" pill for a list row (fetches its own flag). */
export function RowForYou({ documentId }: { documentId: string }) {
  const f = useFlags([documentId])[documentId];
  return <ForYouPill documentId={documentId} flag={f} />;
}

/** Circular page: who it applies to, For you, and Applies to me / Not for me. */
export function AppliesBar({ documentId }: { documentId: string }) {
  // Read after mount: the public circular page is rendered on the server, where nobody is signed in.
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => setSignedIn(!!getStoredUser()), []);
  const flag = useFlags([documentId])[documentId];
  const [busy, setBusy] = useState(false);
  if (!signedIn || !flag) return null;
  const set = async (v: -1 | 0 | 1) => {
    setBusy(true);
    try {
      await markCircular(documentId, flag.mark === v ? 0 : v);
    } finally {
      setBusy(false);
    }
  };
  const who = flag.applies_to.length ? `Applies to ${flag.applies_to.map((w) => (w.startsWith("Islamic") ? w : w.charAt(0).toLowerCase() + w.slice(1))).join(", ")}` : "";
  return (
    <div className={`mt-3 flex flex-wrap items-center justify-between gap-2 rounded-[10px] border px-3 py-2 ${flag.for_you ? "border-accent/50" : "border-line"}`}>
      <span className="flex min-w-0 flex-wrap items-center gap-2 text-[13.5px] text-ink-2">
        {flag.for_you && <ForYouPill documentId={documentId} flag={flag} />}
        <span>{who || (flag.for_you ? flag.reason : "Does this circular apply to you?")}</span>
      </span>
      <span className="flex gap-1.5">
        <button type="button" disabled={busy} aria-pressed={flag.mark === 1} onClick={() => set(1)} className={`${chip(flag.mark === 1)} inline-flex items-center gap-1 py-1 text-[12.5px]`}>
          <Check className="h-3.5 w-3.5" strokeWidth={2} /> Applies to me
        </button>
        <button type="button" disabled={busy} aria-pressed={flag.mark === -1} onClick={() => set(-1)} className={`${chip(flag.mark === -1)} py-1 text-[12.5px]`}>
          Not for me
        </button>
      </span>
    </div>
  );
}

const DISMISS_KEY = "amar_institution_card_dismissed";

/** Dashboard: shown once to readers whose institution type we could not work out. */
export function InstitutionCard({ signedIn }: { signedIn: boolean }) {
  const [me, setMe] = useAudienceMe(signedIn);
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<string | null>(null);
  const [hasAd, setHasAd] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [hidden, setHidden] = useState(true);
  useEffect(() => setHidden(typeof window !== "undefined" && localStorage.getItem(DISMISS_KEY) === "1"), []);
  if (!signedIn || !me || me.institution_type || hidden) return null;
  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, "1");
    setHidden(true);
  };
  const save = async () => {
    if (!kind) return;
    setBusy(true);
    try {
      setMe(await saveInstitution(kind, hasAd));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mx-auto mt-4 max-w-[760px] rounded-[12px] border border-accent/40 bg-accent-soft px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[15px] font-bold text-accent">Tell us your institution type</p>
          <p className="text-[13px] text-accent/80">We&apos;ll flag the circulars that apply to you.</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {!open && (
            <button type="button" onClick={() => setOpen(true)} className="btn-primary h-9 px-3 text-[13px]">
              Choose
            </button>
          )}
          <button type="button" onClick={dismiss} aria-label="Dismiss" className="grid h-9 w-9 place-items-center rounded-control text-accent hover:bg-surface/60">
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
      {open && (
        <div className="mt-3 rounded-[10px] bg-surface p-3">
          <InstitutionPicker kinds={me.kinds} kind={kind} hasAd={hasAd} onChange={(k, a) => (setKind(k), setHasAd(a))} />
          <button type="button" disabled={!kind || busy} onClick={save} className="btn-primary mt-3 h-9 px-4 text-[13px]">
            {busy ? "Saving..." : "Save"}
          </button>
        </div>
      )}
    </div>
  );
}

/** Account window: institution type (changeable) and what we have learned from the reader's marks. */
export function AccountInstitution() {
  const [me, setMe] = useAudienceMe(true);
  const [editing, setEditing] = useState(false);
  const [kind, setKind] = useState<string | null>(null);
  const [hasAd, setHasAd] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  if (!me) return null;
  const startEdit = () => {
    setKind(me.institution_type);
    setHasAd(me.has_ad);
    setEditing(true);
  };
  const save = async () => {
    setBusy(true);
    try {
      setMe(await saveInstitution(kind, hasAd));
      setEditing(false);
    } finally {
      setBusy(false);
    }
  };
  const bank = me.kinds.find((k) => k.code === me.institution_type)?.bank;
  const current = me.institution_label ? `${me.institution_label}${bank ? (me.has_ad ? " · AD branches" : " · no AD branches") : ""}` : "Not set";
  const tags = (list: AudienceMe["interests"]) =>
    list.map((i) => (
      <span key={i.tag} className="inline-flex items-center gap-1 rounded-full border border-line px-2.5 py-1 text-[12.5px] font-semibold text-ink-2">
        {i.label}
        <button type="button" aria-label={`Remove ${i.label}`} onClick={async () => setMe(await muteInterest(i.tag))} className="text-ink-3 hover:text-ink">
          <X className="h-3.5 w-3.5" />
        </button>
      </span>
    ));
  return (
    <div className="space-y-3 border-b border-line pb-4">
      <div>
        <div className="flex items-center justify-between gap-3">
          <p className="text-[12.5px] text-ink-3">Institution type</p>
          {!editing && (
            <button type="button" onClick={startEdit} className="text-[13px] font-semibold text-accent hover:underline">
              Change
            </button>
          )}
        </div>
        {!editing ? (
          <p className="mt-0.5 text-[14px] font-semibold text-ink">{current}</p>
        ) : (
          <div className="mt-2">
            <InstitutionPicker kinds={me.kinds} kind={kind} hasAd={hasAd} onChange={(k, a) => (setKind(k), setHasAd(a))} />
            <div className="mt-3 flex gap-2">
              <button type="button" disabled={!kind || busy} onClick={save} className="btn-primary h-9 px-4 text-[13px]">
                {busy ? "Saving..." : "Save"}
              </button>
              <button type="button" onClick={() => setEditing(false)} className="btn-secondary h-9 px-3 text-[13px]">
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
      {me.interests.length > 0 && (
        <div>
          <p className="mb-1.5 text-[12.5px] text-ink-3">Your interests</p>
          <div className="flex flex-wrap gap-1.5">{tags(me.interests)}</div>
        </div>
      )}
      {me.not_interested.length > 0 && (
        <div>
          <p className="mb-1.5 text-[12.5px] text-ink-3">Not interested</p>
          <div className="flex flex-wrap gap-1.5">{tags(me.not_interested)}</div>
        </div>
      )}
    </div>
  );
}
