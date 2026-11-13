"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Check, X } from "lucide-react";
import { Notice, SkeletonLine } from "@/components/ui";
import AdminEmailBox from "@/components/alerts/AdminEmailBox";
import SignInPrompt from "@/components/alerts/SignInPrompt";
import { useSessionUser } from "@/components/workspace/Shell";
import type { EmailMode, PreferencesRead } from "@/services/alertsApi";
import {
  addKeyword,
  loadPrefs,
  removeKeyword,
  setChannel,
  setEmailEnabled,
  toggleDepartment,
  toggleDocumentType,
  useAlerts,
} from "@/services/alertsStore";

const MODES: { id: EmailMode; label: string }[] = [
  { id: "OFF", label: "Off" },
  { id: "INSTANT", label: "Right away" },
  { id: "DIGEST", label: "Daily summary" },
];

function readable(raw: string) {
  const s = raw.replace(/_/g, " ").toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const chipCls = (on: boolean) =>
  `inline-flex min-h-[44px] items-center rounded-full border px-3.5 text-[13.5px] font-semibold transition-colors sm:min-h-[36px] ${
    on ? "border-accent bg-accent-soft text-accent" : "border-line-strong bg-surface text-ink-2 hover:bg-sunken"
  }`;

function SavedMark({ pending, savedAt }: { pending: number; savedAt: number }) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (!savedAt) return;
    setShow(true);
    const t = setTimeout(() => setShow(false), 1500);
    return () => clearTimeout(t);
  }, [savedAt]);
  return (
    <span className="inline-flex h-6 items-center gap-1 text-[13px] font-semibold text-ok" role="status" aria-live="polite" data-testid="saved-mark">
      {pending > 0 ? (
        <span className="font-medium text-ink-3">Saving...</span>
      ) : show ? (
        <>
          <Check className="h-3.5 w-3.5" strokeWidth={2.4} aria-hidden />
          Saved
        </>
      ) : null}
    </span>
  );
}

function summaryOf(p: PreferencesRead): string {
  const parts: string[] = [];
  if (p.library_department_codes.length) parts.push(`from ${p.library_department_codes.join(", ")}`);
  if (p.library_document_types.length) parts.push(`of type ${p.library_document_types.map(readable).join(", ")}`);
  if (p.library_keywords.length) parts.push(`that mention ${p.library_keywords.map((k) => `"${k}"`).join(" or ")}`);
  return parts.length ? `circulars ${parts.join(", ")}` : "all new circulars";
}

export default function AlertSettingsPage() {
  const { user, ready, setUser } = useSessionUser();
  if (!ready) return <SkeletonLine className="h-24 w-full" />;
  if (!user) return <SignInPrompt user={user} setUser={setUser} />;
  return <Settings email={user.email} isStaff={user.is_superuser} />;
}

function Settings({ email, isStaff }: { email: string; isStaff: boolean }) {
  const s = useAlerts();
  const p = s.prefs;
  const [word, setWord] = useState("");
  const [wordError, setWordError] = useState<string | null>(null);

  useEffect(() => {
    void loadPrefs();
  }, []);

  const header = (
    <div className="flex flex-wrap items-center gap-3">
      <Link href="/alerts" className="btn-ghost -ml-2 min-h-[44px] sm:min-h-0" aria-label="Back to alerts">
        <ArrowLeft className="h-4 w-4" strokeWidth={1.8} />
        Alerts
      </Link>
      <SavedMark pending={s.prefsPending} savedAt={s.prefsSavedAt} />
    </div>
  );

  if (!p) {
    return (
      <div className="mx-auto max-w-[760px] space-y-4">
        {header}
        <h1 className="text-[22px] font-bold tracking-tight text-ink">Alert settings</h1>
        {typeof s.prefsLoaded === "object" ? (
          <Notice kind="error">
            <span>{s.prefsLoaded.error} </span>
            <button type="button" className="font-semibold underline" onClick={() => void loadPrefs(true)}>
              Try again
            </button>
          </Notice>
        ) : (
          <div className="space-y-3" aria-busy="true" aria-label="Loading">
            {[0, 1, 2].map((i) => (
              <SkeletonLine key={i} className="h-16 w-full" />
            ))}
          </div>
        )}
        {isStaff && <AdminEmailBox />}
      </div>
    );
  }

  const emailOn = p.email_configured || s.emailConfigured;
  const emailLocked = !emailOn || !p.email_enabled;
  const library = p.channels.library;
  const libraryOn = !!library && (library.in_app || library.email !== "OFF");

  const submitWord = () => {
    if (!word.trim()) return;
    const problem = addKeyword(word);
    setWordError(problem);
    if (!problem) setWord("");
  };

  return (
    <div className="mx-auto max-w-[760px] space-y-5">
      {header}
      <div>
        <h1 className="text-[22px] font-bold tracking-tight text-ink">Alert settings</h1>
        <p className="mt-1 text-[14px] text-ink-2" data-testid="email-line">
          {emailOn ? `Emails go to ${email}.` : "Email is not set up on this server. You will see alerts here in the app."}
        </p>
      </div>

      <div className="panel flex min-h-[44px] items-center justify-between gap-4 px-4 py-2">
        <div className="min-w-0">
          <p className="text-[14.5px] font-semibold text-ink" id="email-switch-label">
            Send me email
          </p>
          {!emailOn && <p className="text-[13px] text-ink-3">Not available: email is not set up on this server.</p>}
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={p.email_enabled}
          aria-labelledby="email-switch-label"
          disabled={!emailOn}
          onClick={() => setEmailEnabled(!p.email_enabled)}
          className="grid h-11 w-14 shrink-0 place-items-center disabled:cursor-not-allowed disabled:opacity-50"
        >
          <span className={`relative block h-7 w-12 rounded-full transition-colors ${p.email_enabled && emailOn ? "bg-accent" : "bg-line-strong"}`}>
            <span className={`absolute top-0.5 h-6 w-6 rounded-full bg-surface shadow transition-all ${p.email_enabled && emailOn ? "left-[22px]" : "left-0.5"}`} />
          </span>
        </button>
      </div>

      <section aria-labelledby="what-title" className="panel overflow-hidden">
        <div className="hidden grid-cols-[minmax(0,1fr)_96px_300px] items-center gap-3 border-b border-line bg-sunken/60 px-4 py-2 text-[13px] font-semibold text-ink-3 sm:grid">
          <h2 id="what-title">What to tell me about</h2>
          <span>In the app</span>
          <span>Email</span>
        </div>
        <h2 className="border-b border-line px-4 py-3 text-[15px] font-semibold text-ink sm:hidden">What to tell me about</h2>
        <ul>
          {p.options.groups.map((g) => {
            const ch = p.channels[g.id] ?? { in_app: true, email: "OFF" as EmailMode };
            return (
              <li key={g.id} className="grid gap-2 border-b border-line px-4 py-3 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_96px_300px] sm:items-center sm:gap-3" data-testid={`group-${g.id}`}>
                <div className="min-w-0">
                  <p className="text-[14.5px] font-semibold text-ink">{g.label}</p>
                  <p className="text-[13px] leading-snug text-ink-3">{g.description}</p>
                </div>
                <label className="flex min-h-[44px] cursor-pointer items-center gap-2.5 text-[14px] text-ink-2">
                  <input
                    type="checkbox"
                    className="h-5 w-5 accent-[rgb(var(--accent))]"
                    checked={ch.in_app}
                    aria-label={`In the app: ${g.label}`}
                    onChange={(e) => setChannel(g.id, { in_app: e.target.checked })}
                  />
                  <span className="sm:sr-only">Show in the app</span>
                </label>
                <div role="radiogroup" aria-label={`Email: ${g.label}`} className="flex rounded-control border border-line-strong bg-surface p-0.5">
                  {MODES.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      role="radio"
                      aria-checked={ch.email === m.id}
                      disabled={emailLocked}
                      onClick={() => setChannel(g.id, { email: m.id })}
                      className={`min-h-[44px] flex-1 whitespace-nowrap rounded-[5px] px-1.5 text-[13px] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-[34px] ${
                        ch.email === m.id ? "bg-accent text-accent-ink" : "text-ink-2 hover:bg-sunken"
                      }`}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              </li>
            );
          })}
        </ul>
        <p className="border-t border-line bg-sunken/40 px-4 py-2.5 text-[13px] text-ink-3">
          Daily summary: one email a day at {p.digest_time} (Dhaka time).
        </p>
      </section>

      {libraryOn && (
        <section aria-labelledby="library-title" className="panel space-y-5 p-4 sm:p-5" data-testid="library-filters">
          <h2 id="library-title" className="text-[16px] font-semibold text-ink">
            New circulars: only these
          </h2>

          <div>
            <p className="field-label">Departments</p>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Departments">
              {p.options.department_codes.map((d) => {
                const on = p.library_department_codes.includes(d.code);
                return (
                  <button key={d.code} type="button" aria-pressed={on} title={d.name} onClick={() => toggleDepartment(d.code)} className={chipCls(on)}>
                    {d.code}
                  </button>
                );
              })}
            </div>
            {p.library_department_codes.length === 0 && <p className="mt-1.5 text-[13px] text-ink-3">All departments</p>}
          </div>

          <div>
            <p className="field-label">Document types</p>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Document types">
              {p.options.document_types.map((t) => {
                const on = p.library_document_types.includes(t);
                return (
                  <button key={t} type="button" aria-pressed={on} onClick={() => toggleDocumentType(t)} className={chipCls(on)}>
                    {readable(t)}
                  </button>
                );
              })}
            </div>
            {p.library_document_types.length === 0 && <p className="mt-1.5 text-[13px] text-ink-3">All types</p>}
          </div>

          <div>
            <label className="field-label" htmlFor="keyword-input">
              Keywords
            </label>
            <div className="flex gap-2">
              <input
                id="keyword-input"
                className="field min-h-[44px] sm:min-h-0"
                value={word}
                maxLength={60}
                placeholder="Add a word or phrase"
                onChange={(e) => {
                  const v = e.target.value;
                  setWordError(null);
                  if (!v.includes(",")) {
                    setWord(v);
                    return;
                  }
                  // A comma ends a keyword (also when it is pasted or typed on a phone keyboard).
                  const parts = v.split(",");
                  const rest = parts.pop() ?? "";
                  let problem: string | null = null;
                  for (const part of parts) if (part.trim()) problem = addKeyword(part) ?? problem;
                  setWordError(problem);
                  setWord(rest);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === ",") {
                    e.preventDefault();
                    submitWord();
                  }
                }}
              />
              <button type="button" className="btn-secondary min-h-[44px] sm:min-h-0" onClick={submitWord} disabled={!word.trim()}>
                Add
              </button>
            </div>
            {wordError && (
              <p className="mt-1.5 text-[13px] text-bad" role="alert">
                {wordError}
              </p>
            )}
            <p className="mt-1.5 text-[13px] text-ink-3">We check the circular&apos;s reference number and title. Leave empty for all circulars.</p>
            {p.library_keywords.length > 0 && (
              <ul className="mt-2 flex flex-wrap gap-2">
                {p.library_keywords.map((k) => (
                  <li key={k} className="inline-flex items-center rounded-full border border-accent bg-accent-soft pl-3.5 text-[13.5px] font-semibold text-accent">
                    {k}
                    <button type="button" onClick={() => removeKeyword(k)} aria-label={`Remove ${k}`} className="grid h-11 w-11 place-items-center sm:h-9 sm:w-9">
                      <X className="h-3.5 w-3.5" strokeWidth={2.2} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <p className="rounded-control bg-sunken/70 px-3 py-2 text-[13.5px] text-ink-2" data-testid="library-summary">
            You will get alerts for: <span className="font-semibold text-ink">{summaryOf(p)}</span>.
          </p>
        </section>
      )}

      {isStaff && <AdminEmailBox />}
    </div>
  );
}
