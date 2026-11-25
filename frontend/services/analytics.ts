"use client";

import posthog from "posthog-js";
import type { AuthUser } from "./api";

/**
 * Visitor analytics (PostHog): page views, time on page, clicks, session replays, and who the signed-in reader is.
 * Runs only on the live site, so local testing never adds fake visits. Set NEXT_PUBLIC_POSTHOG_KEY to override the key.
 * Traffic goes through /ingest on our own domain (next.config.js) so ad blockers do not drop it.
 */
const KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY || "phc_sP95nqxmXLz5pS5QxaXcVxm856LEzHQS87MUj43gMZfg";
const LIVE_HOSTS = ["amarcircular.com", "www.amarcircular.com"];

let started = false;

function enabled(): boolean {
  if (typeof window === "undefined" || !KEY.startsWith("phc_")) return false;
  return LIVE_HOSTS.includes(window.location.hostname) || process.env.NEXT_PUBLIC_POSTHOG_ANY_HOST === "1";
}

export function startAnalytics() {
  if (started || !enabled()) return;
  started = true;
  posthog.init(KEY, {
    api_host: "/ingest",
    ui_host: "https://us.posthog.com",
    defaults: "2025-11-30", // page views on every in-app navigation, page-leave with time on page
    person_profiles: "always", // a profile for every visitor, signed in or not
    capture_pageleave: true,
    autocapture: true,
    enable_heatmaps: true,
    capture_dead_clicks: true,
    session_recording: {
      maskAllInputs: true, // typed text (passwords, emails) never leaves the browser
    },
    before_send: (event) => {
      if (event && (event.event === "$pageview" || event.event === "$pageleave")) {
        event.properties = { ...event.properties, page_title: document.title };
      }
      return event;
    },
  });
}

/** Ties the visitor's past and future visits to their account. */
export function identifyUser(user: AuthUser | null) {
  if (!started) return;
  if (!user) {
    // Signed out: start a fresh anonymous visitor, but only if this browser was tied to someone.
    if (posthog.get_property("$user_state") === "identified") posthog.reset();
    return;
  }
  posthog.identify(user.id, {
    email: user.email,
    name: user.full_name,
    phone: user.phone_number || undefined,
    is_admin: user.is_superuser,
  });
}

/** Company, designation and the like, as the reader enters them. */
export function setPersonDetails(details: Record<string, string | undefined>) {
  if (!started) return;
  const clean = Object.fromEntries(Object.entries(details).filter(([, v]) => v && v.trim()));
  if (Object.keys(clean).length) posthog.setPersonProperties(clean);
}

/** A named action worth counting on its own (asked a question, downloaded a PDF, ...). */
export function track(event: string, properties?: Record<string, unknown>) {
  if (!started) return;
  posthog.capture(event, properties);
}
