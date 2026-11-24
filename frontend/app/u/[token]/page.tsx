"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { unsubscribeDigest } from "@/services/api";
import { Notice } from "@/components/ui";

/** The "Unsubscribe" link in an email footer: one button, no sign-in. */
export default function UnsubscribePage() {
  const params = useParams<{ token: string }>();
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const go = async () => {
    setState("busy");
    setError(null);
    try {
      setMessage(await unsubscribeDigest(params?.token || ""));
      setState("done");
    } catch (err: any) {
      setError(err?.message || "Could not unsubscribe. Please try again.");
      setState("idle");
    }
  };

  return (
    <div className="mx-auto max-w-[480px] py-10 sm:py-16" data-free-click>
      <h1 className="font-serif text-[32px] font-medium leading-tight text-ink">Unsubscribe from the daily digest</h1>
      <div className="mt-6 space-y-3 rounded-[14px] border border-line bg-surface p-5">
        {error && <Notice kind="error">{error}</Notice>}
        {state === "done" ? (
          <>
            <Notice kind="success">{message}</Notice>
            <Link href="/alerts/settings" className="inline-block text-[14px] font-semibold text-accent hover:underline">
              Email settings
            </Link>
          </>
        ) : (
          <>
            <p className="text-[15px] leading-relaxed text-ink-2">You will stop getting the daily email of new circulars. Alerts about your team&apos;s work are not affected.</p>
            <button type="button" onClick={go} disabled={state === "busy"} className="btn-primary">
              {state === "busy" ? "Please wait..." : "Unsubscribe"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
