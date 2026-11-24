"use client";

import React, { useEffect, useState } from "react";
import { AuthUser, OPEN_REGISTER_EVENT, quickRegister } from "../services/api";
import { Modal, ModalHeader, Notice } from "./ui";
import AuthForm, { type AuthMode } from "./AuthForm";

type Field = "full_name" | "email" | "phone_number" | "company" | "designation";

const FIELDS: { key: Field; label: string; type: string; autoComplete: string; placeholder: string }[] = [
  { key: "full_name", label: "Full name", type: "text", autoComplete: "name", placeholder: "Your name" },
  { key: "email", label: "Work email", type: "email", autoComplete: "email", placeholder: "you@bank.com" },
  { key: "phone_number", label: "Phone number", type: "tel", autoComplete: "tel", placeholder: "+880 1XXX-XXXXXX" },
  { key: "company", label: "Company", type: "text", autoComplete: "organization", placeholder: "Bank or company name" },
  { key: "designation", label: "Designation", type: "text", autoComplete: "organization-title", placeholder: "e.g. Compliance Officer" },
];

const EMPTY: Record<Field, string> = { full_name: "", email: "", phone_number: "", company: "", designation: "" };

/** "Register now": five details, no password. Also offers password sign-in for existing accounts (admins, banks). */
function RegisterForm({ onDone, onSignIn }: { onDone: (u: AuthUser) => void; onSignIn: () => void }) {
  const [values, setValues] = useState<Record<Field, string>>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const v = Object.fromEntries(Object.entries(values).map(([k, x]) => [k, x.trim()])) as Record<Field, string>;
    const missing = FIELDS.find((f) => !v[f.key]);
    if (missing) return setError(`Please enter your ${missing.label.toLowerCase()}.`);
    if (v.phone_number.replace(/\D/g, "").length < 6) return setError("Please enter a valid phone number.");
    setLoading(true);
    try {
      const user = await quickRegister(v);
      setValues(EMPTY);
      onDone(user);
    } catch (err: any) {
      const msg: string = err?.message || "";
      setError(/valid email/i.test(msg) ? "That email address does not look right." : msg || "Could not register. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3.5" noValidate>
      {error && <Notice kind="error">{error}</Notice>}
      {FIELDS.map((f) => (
        <div key={f.key}>
          <label htmlFor={`reg-${f.key}`} className="field-label">
            {f.label}
          </label>
          <input
            id={`reg-${f.key}`}
            type={f.type}
            autoComplete={f.autoComplete}
            placeholder={f.placeholder}
            value={values[f.key]}
            onChange={(e) => setValues((s) => ({ ...s, [f.key]: e.target.value }))}
            className="field"
            required
          />
        </div>
      ))}
      <button type="submit" disabled={loading} className="btn-primary w-full justify-center">
        {loading ? "Registering..." : "Register now"}
      </button>
      <p className="text-center text-[13px] text-ink-3">
        Free access to every Bangladesh Bank circular.{" "}
        <button type="button" onClick={onSignIn} className="font-semibold text-accent hover:underline">
          Have a password? Sign in
        </button>
      </p>
    </form>
  );
}

/**
 * Visitors see the dashboard without an account. Any click on the page (a circular, a filter, a button)
 * opens this dialog instead; once registered, the click works normally. The header button opens it too.
 */
export default function RegisterGate({ signedIn, onUserChange }: { signedIn: boolean; onUserChange?: (u: AuthUser) => void }) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<"register" | AuthMode>("register");

  useEffect(() => {
    const show = () => {
      setView("register");
      setOpen(true);
    };
    window.addEventListener(OPEN_REGISTER_EVENT, show);
    return () => window.removeEventListener(OPEN_REGISTER_EVENT, show);
  }, []);

  useEffect(() => {
    if (signedIn) {
      setOpen(false);
      return;
    }
    // Capture phase: runs before React's own handlers and before links navigate.
    const gate = (e: Event) => {
      const t = e.target as Element | null;
      if (!t || typeof t.closest !== "function") return;
      // Inside a dialog (this one), and controls marked as always free (theme, the register button itself).
      if (t.closest('[role="dialog"], [data-free-click]')) return;
      e.preventDefault();
      e.stopPropagation();
      if (e.type === "click" || e.type === "submit") {
        (document.activeElement as HTMLElement | null)?.blur?.();
        setView("register");
        setOpen(true);
      }
    };
    const focusGate = (e: Event) => {
      const t = e.target as Element | null;
      if (!t || typeof t.closest !== "function" || t.closest('[role="dialog"], [data-free-click]')) return;
      // Typing in the search box or a field also asks to register (keyboard users included).
      if (t.matches("input, textarea, select")) {
        (t as HTMLElement).blur();
        setView("register");
        setOpen(true);
      }
    };
    document.addEventListener("click", gate, true);
    document.addEventListener("submit", gate, true);
    document.addEventListener("auxclick", gate, true);
    document.addEventListener("focusin", focusGate, true);
    return () => {
      document.removeEventListener("click", gate, true);
      document.removeEventListener("submit", gate, true);
      document.removeEventListener("auxclick", gate, true);
      document.removeEventListener("focusin", focusGate, true);
    };
  }, [signedIn]);

  const done = (u: AuthUser) => {
    onUserChange?.(u);
    setOpen(false);
  };

  return (
    <Modal open={open} onClose={() => setOpen(false)} labelledBy="register-title" width="max-w-md">
      {view === "register" ? (
        <>
          <ModalHeader
            id="register-title"
            title="Register now"
            subtitle="Register free to open circulars, summaries, search and alerts."
            onClose={() => setOpen(false)}
          />
          <div className="px-5 py-5">
            <RegisterForm onDone={done} onSignIn={() => setView("signin")} />
          </div>
        </>
      ) : (
        <>
          <ModalHeader id="register-title" title="Sign in" subtitle="For accounts with a password." onClose={() => setOpen(false)} />
          <div className="px-5 py-5">
            <AuthForm mode="signin" onModeChange={() => setView("register")} onDone={done} />
          </div>
        </>
      )}
    </Modal>
  );
}
