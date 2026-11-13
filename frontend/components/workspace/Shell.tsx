"use client";

import { useEffect, useState } from "react";
import { Lock } from "lucide-react";
import AccountModal from "../AccountModal";
import { Notice, SkeletonLine } from "../ui";
import { AUTH_CHANGED_EVENT, AuthUser, getStoredUser } from "@/services/api";
import { clearNotice, syncSessionUser, useWorkspace } from "@/services/workspaceStore";

/** The signed-in user, kept in step with sign-in and sign-out. `ready` is false until the stored session has been read. */
export function useSessionUser(): { user: AuthUser | null; ready: boolean; setUser: (u: AuthUser | null) => void } {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const read = () => {
      setUser(getStoredUser());
      syncSessionUser();
    };
    read();
    setReady(true);
    window.addEventListener(AUTH_CHANGED_EVENT, read);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, read);
  }, []);
  return { user, ready, setUser };
}

/** Shown to people who are not signed in. */
export function SignInGate({ user, setUser }: { user: AuthUser | null; setUser: (u: AuthUser | null) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mx-auto max-w-lg rounded-panel border border-line bg-sunken/60 px-5 py-8 text-center">
      <Lock className="mx-auto h-6 w-6 text-ink-3" strokeWidth={1.75} />
      <h1 className="mt-3 text-[18px] font-semibold text-ink">Sign in to use your bank&apos;s workspace</h1>
      <p className="mt-1 text-[14px] text-ink-2">Registers, tasks and evidence are private to your bank.</p>
      <button type="button" className="btn-primary mt-4 min-h-[44px] sm:min-h-0" onClick={() => setOpen(true)}>
        Sign in
      </button>
      <AccountModal isOpen={open} onClose={() => setOpen(false)} currentUser={user} onUserChange={setUser} />
    </div>
  );
}

/** A short message that stays on screen for a few seconds after a save, or until dismissed when it is an error. */
export function Toast() {
  const ws = useWorkspace();
  if (!ws.notice) return null;
  return (
    <div className="no-print pointer-events-none fixed inset-x-4 bottom-4 z-[65] flex justify-center sm:inset-x-auto sm:right-6 sm:justify-end" data-testid="toast">
      <div className="pointer-events-auto w-full max-w-md shadow-pop">
        <Notice kind={ws.notice.kind} onDismiss={clearNotice}>
          {ws.notice.text}
        </Notice>
      </div>
    </div>
  );
}

export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="rounded-panel border border-line p-4">
          <SkeletonLine className="h-4 w-2/3" />
          <SkeletonLine className="mt-2 h-3 w-1/3" />
        </div>
      ))}
    </div>
  );
}

export function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Notice kind="error">
      <span>{message}</span>
      <button type="button" className="btn-secondary ml-3 min-h-[44px] sm:min-h-0" onClick={onRetry}>
        Try again
      </button>
    </Notice>
  );
}
