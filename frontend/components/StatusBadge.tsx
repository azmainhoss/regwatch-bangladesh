import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  CircleDashed,
  Clock,
  Copy,
  Eye,
  History,
  Loader2,
  Lock,
  RotateCw,
  ScanText,
  type LucideIcon,
} from "lucide-react";

export type Tone = "ok" | "warn" | "bad" | "info" | "muted" | "accent";

interface StatusSpec {
  label: string;
  tone: Tone;
  icon: LucideIcon;
  hint?: string;
  spin?: boolean;
}

/**
 * One place that knows every status string the backend sends: document publication
 * states, discovery states, run states and page reading states. Unknown values still
 * render, as a neutral badge with the raw text made readable.
 */
const STATUSES: Record<string, StatusSpec> = {
  // Documents
  PUBLISHED_HUMAN_REVIEWED: { label: "Signed off", tone: "ok", icon: CheckCircle2, hint: "Checked and signed off by a compliance officer" },
  PUBLISHED_MACHINE_VERIFIED: { label: "Machine verified", tone: "info", icon: CheckCircle2, hint: "Quotes matched the source; no human sign-off yet" },
  PUBLISHED_MACHINE_PROCESSED: { label: "Not signed off", tone: "info", icon: Eye, hint: "Machine analysis, waiting for a compliance officer to sign off" },
  AWAITING_REVIEW: { label: "Awaiting review", tone: "warn", icon: Clock },
  NEEDS_REVISION: { label: "Needs revision", tone: "warn", icon: AlertTriangle },
  ANALYZING: { label: "Analysing", tone: "info", icon: Loader2, spin: true },
  EXTRACTION_FAILED: { label: "Extraction failed", tone: "bad", icon: AlertTriangle },
  SUPERSEDED: { label: "Superseded", tone: "muted", icon: History, hint: "A newer version replaces this one" },
  WITHDRAWN: { label: "Withdrawn", tone: "muted", icon: Ban },
  DRAFT: { label: "Draft", tone: "muted", icon: CircleDashed },

  // Discoveries from the website checker
  DISCOVERED: { label: "Found", tone: "info", icon: CircleDashed },
  VALIDATED: { label: "Ready to review", tone: "accent", icon: Eye },
  DOWNLOAD_PENDING: { label: "Download pending", tone: "info", icon: Clock },
  DUPLICATE: { label: "Already in library", tone: "muted", icon: Copy },
  INGESTED: { label: "Added", tone: "ok", icon: CheckCircle2 },
  APPROVED: { label: "Approved", tone: "ok", icon: CheckCircle2 },
  REJECTED: { label: "Rejected", tone: "bad", icon: Ban },
  SKIPPED_REJECTED: { label: "Skipped, rejected before", tone: "muted", icon: Ban, hint: "An admin rejected this file earlier, so it was not downloaded again" },

  // Checker runs
  COMPLETED: { label: "Completed", tone: "ok", icon: CheckCircle2 },
  SUCCESS: { label: "Succeeded", tone: "ok", icon: CheckCircle2 },
  RUNNING: { label: "Running", tone: "info", icon: Loader2, spin: true },
  FAILED: { label: "Failed", tone: "bad", icon: AlertTriangle },
  FAILED_RETRY: { label: "Failed, will retry", tone: "warn", icon: RotateCw, hint: "The check failed and will run again after a pause" },

  // Page reading
  SUCCESS_NATIVE: { label: "Text layer", tone: "ok", icon: ScanText },
  SUCCESS_VISION: { label: "Read from image", tone: "ok", icon: ScanText },
  SUCCESS_VISION_MANUAL: { label: "Read from image", tone: "ok", icon: ScanText },
  PENDING_VISION: { label: "Waiting to be read", tone: "info", icon: Clock, hint: "This page has no usable text layer yet; it is queued to be read from the page image" },
  NEEDS_HUMAN_REVIEW: { label: "Needs human review", tone: "warn", icon: AlertTriangle, hint: "The text on this page looks damaged; a person should check it" },
  LOW_CONFIDENCE: { label: "Low confidence", tone: "warn", icon: AlertTriangle },
  EMPTY: { label: "No text", tone: "muted", icon: CircleDashed },

  // Source access
  CLEAR: { label: "Reachable", tone: "ok", icon: CheckCircle2 },
  RESTRICTED: { label: "Blocked", tone: "bad", icon: Lock },
};

const TONE_CLASS: Record<Tone, string> = {
  ok: "bg-ok-soft text-ok ring-ok/25",
  warn: "bg-warn-soft text-warn ring-warn/30",
  bad: "bg-bad-soft text-bad ring-bad/25",
  info: "bg-info-soft text-info ring-info/25",
  muted: "bg-muted-soft text-muted ring-muted/25",
  accent: "bg-accent-soft text-accent ring-accent/25",
};

function readable(raw: string) {
  const s = raw.replace(/_/g, " ").toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function describeStatus(status?: string | null): StatusSpec {
  if (!status) return { label: "Unknown", tone: "muted", icon: CircleDashed };
  return STATUSES[status] ?? { label: readable(status), tone: "muted", icon: CircleDashed };
}

export default function StatusBadge({ status, size = "md" }: { status?: string | null; size?: "sm" | "md" }) {
  const spec = describeStatus(status);
  const Icon = spec.icon;
  return (
    <span
      title={spec.hint ? `${spec.hint} (${status})` : status ?? undefined}
      className={`inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full font-semibold ring-1 ring-inset ${TONE_CLASS[spec.tone]} ${
        size === "sm" ? "px-1.5 py-px text-2xs" : "px-2 py-0.5 text-xs"
      }`}
    >
      <Icon className={`${size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5"} ${spec.spin ? "animate-spin" : ""}`} strokeWidth={2} aria-hidden />
      {spec.label}
    </span>
  );
}

export function Tag({ children, tone = "muted", title }: { children: React.ReactNode; tone?: Tone; title?: string }) {
  return (
    <span
      title={title}
      className={`inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${TONE_CLASS[tone]}`}
    >
      {children}
    </span>
  );
}

export function PrivateTag() {
  return (
    <Tag tone="muted" title="Private: only you can see this circular">
      <Lock className="h-3 w-3" strokeWidth={2} aria-hidden />
      Private
    </Tag>
  );
}
