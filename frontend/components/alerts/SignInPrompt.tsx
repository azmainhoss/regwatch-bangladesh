"use client";

import { useState } from "react";
import { Bell } from "lucide-react";
import AccountModal from "@/components/AccountModal";
import type { AuthUser } from "@/services/api";

/** Shown to people who are not signed in. */
export default function SignInPrompt({ user, setUser }: { user: AuthUser | null; setUser: (u: AuthUser | null) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mx-auto max-w-lg rounded-panel border border-line bg-sunken/60 px-5 py-8 text-center">
      <Bell className="mx-auto h-6 w-6 text-ink-3" strokeWidth={1.75} />
      <h1 className="mt-3 text-[18px] font-semibold text-ink">Sign in to see your alerts.</h1>
      <p className="mt-1 text-[14px] text-ink-2">New circulars and work for you show up here.</p>
      <button type="button" className="btn-primary mt-4 min-h-[44px] sm:min-h-0" onClick={() => setOpen(true)}>
        Sign in
      </button>
      <AccountModal isOpen={open} onClose={() => setOpen(false)} currentUser={user} onUserChange={setUser} />
    </div>
  );
}
