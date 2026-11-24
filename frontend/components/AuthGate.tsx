"use client";

import { useEffect, useState } from "react";
import { AUTH_CHANGED_EVENT, fetchCurrentUser, getStoredUser } from "../services/api";
import RegisterGate from "./RegisterModal";

type Status = "loading" | "out" | "in";

/**
 * Everyone sees the site. Visitors who have not registered can look at the dashboard, but any click
 * opens the "Register now" dialog (RegisterGate) until they register.
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
  return (
    <>
      <RegisterGate signedIn={status === "in"} />
      {header}
      <main className="mx-auto w-full max-w-[1480px] flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      {footer}
    </>
  );
}
