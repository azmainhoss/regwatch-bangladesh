"use client";

import { useEffect, useState } from "react";
import { AUTH_CHANGED_EVENT, fetchCurrentUser, getStoredUser } from "../services/api";
import AuthForm, { type AuthMode } from "./AuthForm";

type Status = "loading" | "out" | "in";

function Mark() {
  return (
    <span aria-hidden className="relative grid h-9 w-9 place-items-center rounded-[6px] bg-accent text-accent-ink">
      <span className="absolute right-0 top-0 h-3 w-3 rounded-bl-[4px] bg-canvas/90" />
      <span className="mt-1 text-[17px] font-bold leading-none">R</span>
    </span>
  );
}

function SignInScreen() {
  const [mode, setMode] = useState<AuthMode>("signin");
  return (
    <main className="flex min-h-[100dvh] items-center justify-center bg-canvas px-4 py-10">
      <div className="w-full max-w-[400px]">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="flex items-center gap-2.5">
            <Mark />
            <span className="text-[24px] font-bold tracking-tight text-ink">RegWatch</span>
          </div>
          <p className="mt-3 max-w-[340px] text-[15px] leading-snug text-ink-2">
            Bangladesh Bank circulars with page-cited summaries for bank compliance teams.
          </p>
        </div>
        <div className="rounded-panel border border-line bg-surface p-5 shadow-panel sm:p-6">
          <h1 className="mb-4 text-[18px] font-semibold text-ink">{mode === "signin" ? "Sign in" : "Create an account"}</h1>
          <AuthForm mode={mode} onModeChange={setMode} onDone={() => undefined} />
        </div>
      </div>
    </main>
  );
}

/**
 * Signed-out visitors see only the sign-in screen. The page they asked for stays in the address bar
 * and appears as soon as they sign in. The header and footer are only built once someone is signed in.
 */
export default function AuthGate({
  header,
  footer,
  children,
}: {
  header: React.ReactNode;
  footer: React.ReactNode;
  children: React.ReactNode;
}) {
  const [status, setStatus] = useState<Status>("loading");

  useEffect(() => {
    const sync = () => setStatus(getStoredUser() ? "in" : "out");
    sync();
    // Confirm the saved session with the backend; an invalid or expired token clears it and fires AUTH_CHANGED_EVENT.
    if (getStoredUser()) fetchCurrentUser().catch(() => undefined);
    window.addEventListener(AUTH_CHANGED_EVENT, sync);
    const onStorage = (e: StorageEvent) => {
      if (e.key === null || e.key.startsWith("regwatch_")) sync();
    };
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(AUTH_CHANGED_EVENT, sync);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  if (status === "loading") {
    return (
      <div className="grid min-h-[100dvh] place-items-center bg-canvas" role="status" aria-label="Loading">
        <span className="h-6 w-6 animate-spin rounded-full border-2 border-line border-t-accent" />
      </div>
    );
  }
  if (status === "out") return <SignInScreen />;
  return (
    <>
      {header}
      <main className="mx-auto w-full max-w-[1480px] flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      {footer}
    </>
  );
}
