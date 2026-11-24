"use client";

import { useEffect, useState } from "react";
import { fetchUploadStatus, type UploadStatus } from "@/services/api";
import { Notice } from "../ui";

function when(iso: string) {
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** Phase 1: is the laptop sending the analyses of new circulars, and how many wait for one. */
export default function LaptopUploadStatus() {
  const [s, setS] = useState<UploadStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetchUploadStatus()
      .then(setS)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load the upload status."));
  }, []);

  return (
    <div className="space-y-3 border-t border-line px-5 py-5">
      <h3 className="text-[14px] font-semibold text-ink">Analyses from the laptop</h3>
      {error ? (
        <Notice kind="error">{error}</Notice>
      ) : !s ? (
        <p className="text-[13.5px] text-ink-3">Loading...</p>
      ) : !s.enabled ? (
        <p className="max-w-prose text-[13.5px] text-ink-2">
          Uploads are off on this server (no upload token is set). New circulars are analysed here instead, if a model is set up.
        </p>
      ) : (
        <>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-3">
            <div className="min-w-0">
              <dt className="text-[13px] text-ink-3">Last upload</dt>
              <dd className="mt-0.5 text-[14.5px] font-semibold text-ink tabular-nums">{s.last_upload_at ? when(s.last_upload_at) : "None yet"}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-[13px] text-ink-3">New circulars waiting</dt>
              <dd className="mt-0.5 text-[14.5px] font-semibold text-ink tabular-nums">{s.recent_circulars_waiting}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-[13px] text-ink-3">Schedule</dt>
              <dd className="mt-0.5 text-[14.5px] text-ink">Twice a day from the laptop</dd>
            </div>
          </dl>
          {s.stale && s.recent_circulars_waiting > 0 && (
            <Notice kind="warning">
              {s.last_upload_at
                ? `No analysis has arrived for ${Math.floor(s.hours_since_last_upload ?? 0)} hours while new circulars wait.`
                : "No analysis has arrived yet while new circulars wait."}{" "}
              Check the laptop&apos;s RegWatchPhase1Sync task and its log (data\phase1_sync.log).
            </Notice>
          )}
        </>
      )}
    </div>
  );
}
