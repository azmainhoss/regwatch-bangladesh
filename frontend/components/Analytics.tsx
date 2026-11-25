"use client";

import { useEffect } from "react";
import { AUTH_CHANGED_EVENT, getStoredUser } from "../services/api";
import { identifyUser, startAnalytics } from "../services/analytics";

/** Starts visitor analytics once and keeps PostHog told who is signed in. Renders nothing. */
export default function Analytics() {
  useEffect(() => {
    startAnalytics();
    const sync = () => identifyUser(getStoredUser());
    sync();
    window.addEventListener(AUTH_CHANGED_EVENT, sync);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, sync);
  }, []);
  return null;
}
