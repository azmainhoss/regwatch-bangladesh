"use client";

import { useEffect, useState } from "react";
import { Download, X } from "lucide-react";

interface InstallEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: string }>;
}

const VISITS_KEY = "amarcircular_visits";

/** Counts visits: once per browser session. */
function countVisit(): number {
  try {
    let n = parseInt(localStorage.getItem(VISITS_KEY) || "0", 10) || 0;
    if (!sessionStorage.getItem(VISITS_KEY)) {
      sessionStorage.setItem(VISITS_KEY, "1");
      n += 1;
      localStorage.setItem(VISITS_KEY, String(n));
    }
    return n;
  } catch {
    return 0;
  }
}

function earned(visits: number): boolean {
  try {
    return visits >= 3 || localStorage.getItem("amarcircular_saved_once") === "1";
  } catch {
    return false;
  }
}

/**
 * Registers the service worker and offers "Install the app" once, but only after the person has come back for a
 * third visit or has saved a circular, never on a first look.
 */
export default function InstallApp() {
  const [ev, setEv] = useState<InstallEvent | null>(null);
  const [hidden, setHidden] = useState(true);

  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    }
    const visits = countVisit();
    let dismissed = false;
    try {
      dismissed = localStorage.getItem("install-dismissed") === "1";
    } catch {
      /* private window */
    }
    let offered = false;
    const onPrompt = (e: Event) => {
      e.preventDefault();
      setEv(e as InstallEvent);
      offered = true;
      if (!dismissed && earned(visits)) setHidden(false);
    };
    // Saving a circular during this visit earns the offer straight away.
    const onSaved = () => {
      if (offered && !dismissed) setHidden(false);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("amarcircular-saved", onSaved);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("amarcircular-saved", onSaved);
    };
  }, []);

  if (!ev || hidden) return null;
  const close = () => {
    setHidden(true);
    try {
      localStorage.setItem("install-dismissed", "1");
    } catch {
      /* ignore */
    }
  };
  return (
    <div className="fixed inset-x-3 bottom-3 z-50 flex items-center gap-3 rounded-panel border border-line bg-surface px-4 py-3 shadow-pop sm:left-auto sm:right-4 sm:w-96">
      <Download className="h-5 w-5 shrink-0 text-accent" />
      <p className="flex-1 text-[14px] text-ink">Install Amar Circular as an app for one-tap access and alerts.</p>
      <button
        type="button"
        className="btn-primary px-3 py-1.5"
        onClick={async () => {
          await ev.prompt();
          await ev.userChoice.catch(() => undefined);
          close();
        }}
      >
        Install
      </button>
      <button type="button" onClick={close} aria-label="Not now" className="text-ink-3 hover:text-ink">
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
