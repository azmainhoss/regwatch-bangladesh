"use client";

import React, { useEffect, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { AuthUser, OPEN_REGISTER_EVENT, quickRegister } from "../services/api";
import { FREE_LIMIT, FREE_VIEWS_EVENT, freeExhausted } from "../services/freeViews";
import { Modal, ModalHeader, Notice } from "./ui";
import AuthForm from "./AuthForm";

type Field = "full_name" | "email" | "phone_number" | "company" | "designation" | "password";

const FIELDS: { key: Field; label: string; type: string; autoComplete: string; placeholder: string }[] = [
  { key: "full_name", label: "Full name", type: "text", autoComplete: "name", placeholder: "Your name" },
  { key: "email", label: "Work email", type: "email", autoComplete: "email", placeholder: "you@bank.com" },
  { key: "phone_number", label: "Phone number", type: "tel", autoComplete: "tel", placeholder: "+880 1XXX-XXXXXX" },
  { key: "company", label: "Company", type: "text", autoComplete: "organization", placeholder: "Bank or company name" },
  { key: "designation", label: "Designation", type: "text", autoComplete: "organization-title", placeholder: "e.g. Compliance Officer" },
  { key: "password", label: "Password", type: "password", autoComplete: "new-password", placeholder: "At least 8 characters" },
];

const EMPTY: Record<Field, string> = { full_name: "", email: "", phone_number: "", company: "", designation: "", password: "" };

/** Register: name, email, phone, company, designation and a password. Signed in at once. */
function RegisterForm({ onDone, onSignIn }: { onDone: (u: AuthUser) => void; onSignIn: () => void }) {
  const [values, setValues] = useState<Record<Field, string>>(EMPTY);
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const v = { ...values };
    for (const k of Object.keys(v) as Field[]) if (k !== "password") v[k] = v[k].trim();
    const missing = FIELDS.find((f) => !v[f.key]);
    if (missing) return setError(`Please enter your ${missing.label.toLowerCase()}.`);
    if (v.phone_number.replace(/\D/g, "").length < 6) return setError("Please enter a valid phone number.");
    if (v.password.length < 8) return setError("Your password needs at least 8 characters.");
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
    <form onSubmit={submit} className="space-y-3" noValidate>
      {error && <Notice kind="error">{error}</Notice>}
      {FIELDS.map((f) => (
        <div key={f.key}>
          <label htmlFor={`reg-${f.key}`} className="field-label">
            {f.label}
          </label>
          <div className="relative">
            <input
              id={`reg-${f.key}`}
              type={f.key === "password" && showPw ? "text" : f.type}
              autoComplete={f.autoComplete}
              placeholder={f.placeholder}
              value={values[f.key]}
              onChange={(e) => setValues((s) => ({ ...s, [f.key]: e.target.value }))}
              className={`field ${f.key === "password" ? "pr-10" : ""}`}
              required
            />
            {f.key === "password" && (
              <button
                type="button"
                onClick={() => setShowPw((x) => !x)}
                aria-label={showPw ? "Hide password" : "Show password"}
                className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center text-ink-3 hover:text-ink"
              >
                {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            )}
          </div>
        </div>
      ))}
      <button type="submit" disabled={loading} className="btn-primary w-full justify-center">
        {loading ? "Registering..." : "Register now"}
      </button>
      <p className="text-center text-[13.5px] text-ink-3">
        Already registered?{" "}
        <button type="button" onClick={onSignIn} className="font-semibold text-accent hover:underline">
          Sign in
        </button>
      </p>
    </form>
  );
}

/**
 * Visitors read freely for their first week, then up to FREE_LIMIT circulars (services/freeViews.ts). After
 * that, any click opens this dialog. The header buttons and "Register to ..." prompts open it at any time.
 */
export default function RegisterGate({ signedIn }: { signedIn: boolean }) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<"register" | "signin">("register");
  const [exhausted, setExhausted] = useState(false);

  useEffect(() => {
    const show = (e: Event) => {
      setView((e as CustomEvent).detail === "signin" ? "signin" : "register");
      setOpen(true);
    };
    const sync = () => setExhausted(freeExhausted());
    sync();
    window.addEventListener(OPEN_REGISTER_EVENT, show);
    window.addEventListener(FREE_VIEWS_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(OPEN_REGISTER_EVENT, show);
      window.removeEventListener(FREE_VIEWS_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  useEffect(() => {
    if (signedIn) {
      setOpen(false);
      return;
    }
    if (!exhausted) return;
    // Free circulars used up: every click asks to register. Capture phase runs before links and React handlers.
    const gate = (e: Event) => {
      const t = e.target as Element | null;
      if (!t || typeof t.closest !== "function") return;
      if (t.closest('[role="dialog"], [data-free-click]')) return;
      e.preventDefault();
      e.stopPropagation();
      (document.activeElement as HTMLElement | null)?.blur?.();
      setView("register");
      setOpen(true);
    };
    document.addEventListener("click", gate, true);
    document.addEventListener("submit", gate, true);
    document.addEventListener("auxclick", gate, true);
    return () => {
      document.removeEventListener("click", gate, true);
      document.removeEventListener("submit", gate, true);
      document.removeEventListener("auxclick", gate, true);
    };
  }, [signedIn, exhausted]);

  const done = () => setOpen(false);

  return (
    <Modal open={open} onClose={() => setOpen(false)} labelledBy="register-title" width="max-w-md">
      {view === "register" ? (
        <>
          <ModalHeader
            id="register-title"
            title="Register now"
            subtitle={
              exhausted
                ? `You have read your ${FREE_LIMIT} free circulars. Register free to keep reading.`
                : "Free access to every Bangladesh Bank circular, with summaries, search and alerts."
            }
            onClose={() => setOpen(false)}
          />
          <div className="px-5 py-5">
            <RegisterForm onDone={done} onSignIn={() => setView("signin")} />
          </div>
        </>
      ) : (
        <>
          <ModalHeader id="register-title" title="Sign in" subtitle="Use the email and password you registered with." onClose={() => setOpen(false)} />
          <div className="px-5 py-5">
            <AuthForm mode="signin" onModeChange={() => setView("register")} onDone={done} />
          </div>
        </>
      )}
    </Modal>
  );
}
