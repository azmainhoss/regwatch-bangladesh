import Link from "next/link";
import {
  AlertTriangle,
  Ban,
  Check,
  CheckCircle2,
  CircleDashed,
  Clock,
  Copy,
  Eye,
  History,
  Loader2,
  Lock,
  PenLine,
  RotateCw,
  ScanText,
  Replace,
  ShieldOff,
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
  // Reader trust words (owner, 2026-11-24): only "Ready" and "Analysing" (were AI verified / AI draft until 26 Nov), no tooltips.
  PUBLISHED_HUMAN_REVIEWED: { label: "Ready", tone: "ok", icon: CheckCircle2 },
  PUBLISHED_MACHINE_VERIFIED: { label: "Ready", tone: "ok", icon: CheckCircle2 },
  PUBLISHED_MACHINE_PROCESSED: { label: "Analysing", tone: "info", icon: Eye },
  // Read and searchable, not analysed yet (most archive circulars). Readers see no trust badge for these
  // (READER_HIDDEN below): there is no AI output to vouch for. Admin screens still show this label.
  EXTRACTED: { label: "Not analysed", tone: "muted", icon: CircleDashed },
  EXTRACTING: { label: "Reading pages", tone: "info", icon: Loader2, spin: true },
  AWAITING_REVIEW: { label: "Ready", tone: "ok", icon: CheckCircle2 },
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
  NEEDS_HUMAN_REVIEW: { label: "Text may be damaged", tone: "warn", icon: AlertTriangle, hint: "The text on this page looks damaged; it will be read again from the page image" },
  READ_FAILED: { label: "Could not be read", tone: "warn", icon: AlertTriangle, hint: "Every way of reading this page failed, so it has no text yet" },
  LOW_CONFIDENCE: { label: "Low confidence", tone: "warn", icon: AlertTriangle },
  EMPTY: { label: "No text", tone: "muted", icon: CircleDashed },

  // Source access
  CLEAR: { label: "Reachable", tone: "ok", icon: CheckCircle2 },
  RESTRICTED: { label: "Blocked", tone: "bad", icon: Lock },
};

export const TONE_CLASS: Record<Tone, string> = {
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

/** Statuses readers do not get a badge for (see EXTRACTED above). */
const READER_HIDDEN = new Set(["EXTRACTED"]);

export default function StatusBadge({ status, size = "md", reader = false }: { status?: string | null; size?: "sm" | "md"; reader?: boolean }) {
  if (reader && status && READER_HIDDEN.has(status)) return null;
  const spec = describeStatus(status);
  const Icon = spec.icon;
  // Readers: "Ready" is just a green check mark (owner, 2026-11-28).
  if (reader && spec.label === "Ready") {
    return (
      <span role="img" aria-label="Ready" title="Ready" className="inline-flex shrink-0 items-center text-ok">
        <Check className={size === "sm" ? "h-4 w-4" : "h-[18px] w-[18px]"} strokeWidth={2.5} aria-hidden />
      </span>
    );
  }
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


const IN_FORCE_SPEC: Record<string, { label: string; verb: string; tone: Tone; icon: LucideIcon; hint: string }> = {
  IN_FORCE: { label: "In force", verb: "", tone: "ok", icon: CheckCircle2, hint: "No confirmed circular has changed or replaced this one" },
  AMENDED: { label: "Amended", verb: "Amended by", tone: "info", icon: PenLine, hint: "Still in force, but changed by a later circular" },
  REPLACED: { label: "Replaced", verb: "Replaced by", tone: "warn", icon: Replace, hint: "A later circular replaces this one" },
  REPEALED: { label: "Repealed", verb: "Repealed by", tone: "bad", icon: ShieldOff, hint: "A later circular repeals this one" },
};

export interface InForceView {
  status: string;
  byId?: string | null;
  byRef?: string | null;
}

/**
 * Whether a circular is still in force. Only confirmed links count; links awaiting review never change it.
 * With a newer circular known, the badge names it and (unless `plain`) links to it.
 */
export function InForceBadge({ info, size = "md", plain = false, blip = false }: { info?: InForceView | null; size?: "sm" | "md"; plain?: boolean; blip?: boolean }) {
  if (!info) return null;
  const spec = IN_FORCE_SPEC[info.status];
  if (!spec) return null;
  // "In force" as a small green dot (owner, 2026-11-28); Amended / Replaced / Repealed keep their words.
  if (blip && info.status === "IN_FORCE") {
    return (
      <span role="img" aria-label="In force" title="In force" data-testid="in-force-badge" data-status={info.status} className="inline-flex h-4 w-4 shrink-0 items-center justify-center">
        <span className="h-2 w-2 rounded-full bg-ok ring-2 ring-ok/25" />
      </span>
    );
  }
  const Icon = spec.icon;
  const named = info.status !== "IN_FORCE" && info.status !== "AMENDED" && info.byRef ? `${spec.verb} ${info.byRef}` : spec.label;
  const title = info.byRef && info.status !== "IN_FORCE" ? `${spec.verb} ${info.byRef}. ${spec.hint}` : spec.hint;
  const cls = `inline-flex max-w-full shrink-0 items-center gap-1 whitespace-nowrap rounded-full font-semibold ring-1 ring-inset ${TONE_CLASS[spec.tone]} ${
    size === "sm" ? "px-1.5 py-px text-2xs" : "px-2 py-0.5 text-xs"
  }`;
  const inner = (
    <>
      <Icon className={size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5"} strokeWidth={2} aria-hidden />
      <span className="truncate">{named}</span>
    </>
  );
  if (!plain && info.byId && info.status !== "IN_FORCE") {
    return (
      <Link href={`/dashboard?doc=${info.byId}`} title={title} data-testid="in-force-badge" data-status={info.status} className={`${cls} hover:brightness-95`}>
        {inner}
      </Link>
    );
  }
  return (
    <span title={title} data-testid="in-force-badge" data-status={info.status} className={cls}>
      {inner}
    </span>
  );
}

/** Links the automated checks have not settled yet (no person is involved). Shown to admins only. */
export function AwaitingReviewTag({ count }: { count?: number }) {
  return (
    <Tag tone="muted" title="The automated checks are still running on these links. Until they finish, the links do not change any circular's in-force status.">
      <Clock className="h-3 w-3" strokeWidth={2} aria-hidden />
      {typeof count === "number" ? `${count} link${count === 1 ? "" : "s"} being checked` : "Being checked"}
    </Tag>
  );
}
