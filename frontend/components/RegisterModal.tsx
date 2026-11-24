"use client";

import React, { useEffect, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { AuthUser, OPEN_REGISTER_EVENT, quickRegister, updateMyProfile } from "../services/api";
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

// ------------------------------------------------------------------------------------------ 3-step sign-up
// Step 1 makes the account (email + password), so a person who stops after it still has one. Steps 2 and 3 add
// name and phone, then company and designation (owner-approved 2026-11-25).

function StepBar({ step }: { step: 1 | 2 | 3 }) {
  return (
    <div className="mb-4">
      <p className="text-[12.5px] font-semibold text-ink-3">Step {step} of 3</p>
      <div className="mt-1.5 grid grid-cols-3 gap-1.5" aria-hidden>
        {[1, 2, 3].map((n) => (
          <span key={n} className={`h-1.5 rounded-full ${n <= step ? "bg-accent" : "bg-sunken"}`} />
        ))}
      </div>
    </div>
  );
}

function TextField({
  id,
  label,
  type = "text",
  autoComplete,
  placeholder,
  value,
  onChange,
  trailing,
}: {
  id: string;
  label: string;
  type?: string;
  autoComplete: string;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  trailing?: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="field-label">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={type}
          autoComplete={autoComplete}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={`field ${trailing ? "pr-10" : ""}`}
          required
        />
        {trailing}
      </div>
    </div>
  );
}

export function RegisterSteps({
  onDone,
  onSignIn,
  onStarted,
}: {
  onDone: () => void;
  onSignIn: () => void;
  /** Called once the account exists (after step 1), so the dialog stays open for steps 2 and 3. */
  onStarted: () => void;
}) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [v, setV] = useState({ email: "", password: "", full_name: "", phone_number: "", company: "", designation: "" });
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof v) => (val: string) => setV((s) => ({ ...s, [k]: val }));

  const run = async (fn: () => Promise<void>) => {
    setError(null);
    setLoading(true);
    try {
      await fn();
    } catch (err: any) {
      const msg: string = err?.message || "";
      setError(/valid email/i.test(msg) ? "That email address does not look right." : msg || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (step === 1) {
      const email = v.email.trim();
      if (!email) return setError("Please enter your work email.");
      if (v.password.length < 8) return setError("Your password needs at least 8 characters.");
      return run(async () => {
        onStarted();
        await quickRegister({ email, password: v.password });
        setStep(2);
      });
    }
    if (step === 2) {
      const name = v.full_name.trim();
      if (!name) return setError("Please enter your full name.");
      if (v.phone_number.replace(/\D/g, "").length < 6) return setError("Please enter a valid phone number.");
      return run(async () => {
        await updateMyProfile({ full_name: name, phone_number: v.phone_number.trim() });
        setStep(3);
      });
    }
    const company = v.company.trim();
    const designation = v.designation.trim();
    if (!company) return setError("Please enter your company.");
    if (!designation) return setError("Please enter your designation.");
    return run(async () => {
      await updateMyProfile({ company, designation });
      onDone();
    });
  };

  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <StepBar step={step} />
      {error && <Notice kind="error">{error}</Notice>}
      {step === 1 && (
        <>
          <TextField id="rs-email" label="Work email" type="email" autoComplete="email" placeholder="you@bank.com" value={v.email} onChange={set("email")} />
          <TextField
            id="rs-password"
            label="Password"
            type={showPw ? "text" : "password"}
            autoComplete="new-password"
            placeholder="At least 8 characters"
            value={v.password}
            onChange={set("password")}
            trailing={
              <button
                type="button"
                onClick={() => setShowPw((x) => !x)}
                aria-label={showPw ? "Hide password" : "Show password"}
                className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center text-ink-3 hover:text-ink"
              >
                {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            }
          />
        </>
      )}
      {step === 2 && (
        <>
          <TextField id="rs-name" label="Full name" autoComplete="name" placeholder="Your name" value={v.full_name} onChange={set("full_name")} />
          <TextField id="rs-phone" label="Phone number" type="tel" autoComplete="tel" placeholder="+880 1XXX-XXXXXX" value={v.phone_number} onChange={set("phone_number")} />
        </>
      )}
      {step === 3 && (
        <>
          <TextField id="rs-company" label="Company" autoComplete="organization" placeholder="Bank or company name" value={v.company} onChange={set("company")} />
          <TextField
            id="rs-designation"
            label="Designation"
            autoComplete="organization-title"
            placeholder="e.g. Compliance Officer"
            value={v.designation}
            onChange={set("designation")}
          />
        </>
      )}
      <button type="submit" disabled={loading} className="btn-primary w-full justify-center">
        {loading ? "Saving..." : step === 1 ? "Create free account" : step === 2 ? "Continue" : "Finish"}
      </button>
      {step === 1 && (
        <p className="text-center text-[13.5px] text-ink-3">
          Already registered?{" "}
          <button type="button" onClick={onSignIn} className="font-semibold text-accent hover:underline">
            Sign in
          </button>
        </p>
      )}
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
  const [inSteps, setInSteps] = useState(false);

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
      // Mid sign-up the account already exists after step 1: keep the dialog open for steps 2 and 3.
      if (!inSteps) setOpen(false);
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
  }, [signedIn, exhausted, inSteps]);

  const done = () => {
    setInSteps(false);
    setOpen(false);
  };

  return (
    <Modal open={open} onClose={done} labelledBy="register-title" width="max-w-md">
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
            <RegisterSteps onDone={done} onSignIn={() => setView("signin")} onStarted={() => setInSteps(true)} />
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
