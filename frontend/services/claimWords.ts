/**
 * Plain words for everything the checked view says. Internal names (point kinds, states, entity
 * codes) are turned into words here, in one place, so no screen shows them.
 */
import type { ClaimItem, ClaimSection, HiddenPoint, HiddenState } from "./api";

export const KIND_LABEL: Record<string, string> = {
  SUMMARY_POINT: "Summary point",
  KEY_CHANGE: "Change",
  OBLIGATION: "Requirement",
  APPLIES_TO: "Applies to",
  EXEMPTION: "Exception",
  DATE: "Date",
  LINK: "Link",
  PROVISION: "Clause",
};

/** Section order on the circular page. Clauses are not shown there. */
export const SECTION_ORDER: ClaimSection[] = ["summary", "changes", "requirements", "applies_to", "exemptions", "dates", "links"];

/** What one hidden point of a section is called, singular and plural. */
const NOUN: Record<ClaimSection, [string, string]> = {
  summary: ["summary point", "summary points"],
  changes: ["change", "changes"],
  requirements: ["requirement", "requirements"],
  applies_to: ["line about who it applies to", "lines about who it applies to"],
  exemptions: ["exception", "exceptions"],
  dates: ["date", "dates"],
  links: ["link", "links"],
  clauses: ["clause", "clauses"],
};

export const ENTITY_LABELS: Record<string, string> = {
  SCHEDULED_BANK: "All scheduled banks in Bangladesh",
  STATE_OWNED_BANK: "State-owned banks",
  PRIVATE_COMMERCIAL_BANK: "Private commercial banks",
  ISLAMIC_BANK: "Islamic Shariah-based banks",
  FOREIGN_BANK: "Foreign banks",
  SPECIALIZED_BANK: "Specialised banks",
  NBFI: "Non-bank financial institutions",
  AUTHORIZED_DEALER: "Authorised dealers (AD branches)",
  MONEY_CHANGER: "Money changers",
  PAYMENT_SERVICE_PROVIDER: "Payment service providers",
  MOBILE_FINANCIAL_SERVICE: "Mobile financial service providers",
  MICROFINANCE_INSTITUTION: "Microfinance institutions",
  EXCHANGE_HOUSE: "Exchange houses",
  OFFSHORE_BANKING_UNIT: "Offshore banking units",
  // Name used by earlier analyses.
  SCHEDULED_COMMERCIAL_BANK: "All scheduled banks in Bangladesh",
};

export function readable(raw?: string | null): string {
  if (!raw) return "";
  const s = String(raw).replace(/_/g, " ").toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function entityLabel(raw?: string | null): string {
  if (!raw) return "";
  return ENTITY_LABELS[raw] ?? (/^[A-Z_]+$/.test(raw) ? readable(raw) : raw);
}

export function minutesText(m: number): string {
  if (m <= 1) return "about a minute";
  if (m < 60) return `about ${m} minutes`;
  const h = Math.round(m / 60);
  return `about ${h} ${h === 1 ? "hour" : "hours"}`;
}

export function pagesText(pages: number[]): string {
  const sorted = Array.from(new Set(pages)).sort((a, b) => a - b);
  if (sorted.length === 0) return "";
  if (sorted.length === 1) return `page ${sorted[0]}`;
  return `pages ${sorted.slice(0, -1).join(", ")} and ${sorted[sorted.length - 1]}`;
}

export function noun(section: ClaimSection, n: number): string {
  return NOUN[section][n === 1 ? 0 : 1];
}

/** One line for the points of one section that are held back for one reason. */
export interface PlaceholderLine {
  key: string;
  section: ClaimSection;
  state: HiddenState;
  count: number;
  /** The sentence before the page links. */
  before: string;
  pages: number[];
  /** Boxes to mark on a page, by page number (only filled when the lines really are on the page). */
  highlights: Record<number, HiddenPoint["quote_boxes"]>;
  /** True when every point of the line has its lines marked on the page. */
  marked: boolean;
}

function clockTime(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function placeholderLines(hidden: HiddenPoint[], checking: { minutes_left: number; paused_until: string | null }): PlaceholderLine[] {
  const out: PlaceholderLine[] = [];
  const states: HiddenState[] = ["waiting_for_team", "not_shown", "checking"];
  for (const section of SECTION_ORDER) {
    for (const state of states) {
      const group = hidden.filter((h) => h.section === section && h.state === state);
      if (group.length === 0) continue;
      const n = group.length;
      const pages = group.map((h) => h.page_number).filter((p): p is number => typeof p === "number");
      const highlights: Record<number, HiddenPoint["quote_boxes"]> = {};
      for (const h of group) {
        if (h.page_number && h.quote_boxes.length > 0) highlights[h.page_number] = [...(highlights[h.page_number] ?? []), ...h.quote_boxes];
      }
      const marked = pages.length > 0 && group.every((h) => !!h.page_number && h.quote_boxes.length > 0);
      const what = `${n} ${noun(section, n)}`;
      const be = n === 1 ? "is" : "are";
      const it = n === 1 ? "it" : "them";
      let before = "";
      if (state === "waiting_for_team") {
        before = `${what} ${be} waiting for our team to check ${it}, usually within one working day. Until then, `;
      } else if (state === "not_shown") {
        before = `${what} did not pass our checks, so ${n === 1 ? "it is" : "they are"} not shown. `;
      } else if (checking.paused_until) {
        const at = clockTime(checking.paused_until);
        before = `${what} ${be} still being checked against the page image. Checking is paused${at ? ` until about ${at}, when today's free limit resets` : " until today's free limit resets"}. `;
      } else {
        before = `${what} ${be} still being checked against the page image, ${minutesText(checking.minutes_left)} left. This page updates by itself. `;
      }
      out.push({ key: `${section}:${state}`, section, state, count: n, before, pages, highlights, marked });
    }
  }
  return out;
}

export function checkedTag(item: ClaimItem): string {
  if (item.checked_by === "TEAM") return "Checked";
  return item.page_number ? `Checked against page ${item.page_number}` : "Checked";
}

/** The badge a reader sees for the whole circular. */
export function checkedBadge(counts: { total: number; shown: number }, anyByTeam: boolean): { label: string; hint: string; tone: "ok" | "info" } | null {
  if (counts.total === 0) return null;
  if (counts.shown < counts.total) return { label: "Partly checked", hint: "Some points did not pass our checks yet and are not shown", tone: "info" };
  if (anyByTeam) return { label: "Checked", hint: "Every point shown here was checked against the page", tone: "ok" };
  return { label: "Checked", hint: "Every point shown here was checked against the page", tone: "ok" };
}

/** An administrator's plain line for a point that is not shown. */
export function adminStateText(item: ClaimItem): string {
  const why = (item.why ?? []).filter(Boolean).join(" ");
  if (item.status === "WAITING_FOR_PERSON") return why ? `Waiting for a check: ${why}` : "Waiting for a check";
  if (item.status === "CHECKING") return "Still being checked against the page image";
  return why ? `Not shown: ${why}` : "Not shown";
}

// ------------------------------------------------------------------------------------ the review screen

export const REJECT_REASONS: Array<{ id: string; label: string }> = [
  { id: "NOT_IN_CIRCULAR", label: "Not in the circular" },
  { id: "WRONG_DETAILS", label: "Wrong details" },
  { id: "NOT_A_REQUIREMENT", label: "Not a requirement" },
  { id: "OTHER", label: "Other" },
];

export const FIELD_LABEL: Record<string, string> = {
  text: "Wording",
  title: "Title",
  description: "What it says",
  obligation_type: "Kind of requirement",
  who: "Who must do it",
  deadline: "Deadline",
  deadline_text: "Deadline in words",
  effective_date: "Starts on",
  frequency: "How often",
  penalty: "What happens if it is not done",
  clause: "Clause",
  entity: "Who it applies to",
  date_kind: "Kind of date",
  date: "Date",
  claimed_type: "Kind of link",
  target_hint: "Circular it names",
  number: "Clause number",
  heading: "Heading",
  explanation: "What it says",
  provision_type: "Kind of clause",
};

export const OBLIGATION_TYPE_LABEL: Record<string, string> = {
  MANDATORY: "Must be done",
  PROHIBITION: "Must not be done",
  PERMISSION: "Is allowed",
  REPORTING: "Must be reported",
  APPROVAL: "Needs approval",
  RECORD_RETENTION: "Records must be kept",
  DISCLOSURE: "Must be published",
  CONDITIONAL: "Depends on a condition",
  RECOMMENDATION: "Is advised",
};

export const LINK_TYPE_LABEL: Record<string, string> = {
  AMENDS: "Amends",
  REPEALS: "Cancels",
  SUPERSEDES: "Replaces",
  REPLACES: "Replaces",
  REFERENCES: "Mentions",
  CLARIFIES: "Clarifies",
  IMPLEMENTS: "Carries out",
  RELATED_TO: "Is related to",
};

export const DATE_KIND_LABEL: Record<string, string> = {
  EFFECTIVE: "Starts on",
  COMPLIANCE: "To be done by",
  REPORTING: "Report due",
};

export const FREQUENCY_LABEL: Record<string, string> = {
  ONE_TIME: "Once",
  DAILY: "Every day",
  WEEKLY: "Every week",
  FORTNIGHTLY: "Every two weeks",
  MONTHLY: "Every month",
  QUARTERLY: "Every quarter",
  HALF_YEARLY: "Every six months",
  YEARLY: "Every year",
  ANNUAL: "Every year",
  ON_EVENT: "When it happens",
};

export function optionLabel(map: Record<string, string>, raw?: string | null): string {
  if (!raw) return "";
  return map[raw] ?? readable(raw);
}

/** The fields of a point in the order they are shown and edited, with what kind of input each needs. */
export type FieldType = "text" | "longtext" | "date" | "obligation_type" | "entity" | "link_type" | "date_kind" | "frequency";
export const FIELDS_OF_KIND: Record<string, Array<{ key: string; type: FieldType }>> = {
  SUMMARY_POINT: [{ key: "text", type: "longtext" }],
  KEY_CHANGE: [{ key: "text", type: "longtext" }],
  OBLIGATION: [
    { key: "title", type: "text" },
    { key: "description", type: "longtext" },
    { key: "obligation_type", type: "obligation_type" },
    { key: "who", type: "entity" },
    { key: "deadline", type: "date" },
    { key: "deadline_text", type: "text" },
    { key: "effective_date", type: "date" },
    { key: "frequency", type: "frequency" },
    { key: "penalty", type: "text" },
    { key: "clause", type: "text" },
  ],
  APPLIES_TO: [{ key: "entity", type: "entity" }],
  EXEMPTION: [{ key: "text", type: "longtext" }],
  DATE: [
    { key: "date_kind", type: "date_kind" },
    { key: "date", type: "date" },
  ],
  LINK: [
    { key: "claimed_type", type: "link_type" },
    { key: "target_hint", type: "text" },
  ],
  PROVISION: [
    { key: "number", type: "text" },
    { key: "heading", type: "text" },
    { key: "explanation", type: "longtext" },
    { key: "provision_type", type: "text" },
  ],
};

export function formatDate(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

/** One plain value of a field, as a reader would say it. */
export function fieldValueText(key: string, value: any): string {
  if (value === null || value === undefined || value === "") return "";
  const raw = String(value);
  switch (key) {
    case "obligation_type":
      return optionLabel(OBLIGATION_TYPE_LABEL, raw);
    case "who":
    case "entity":
      return entityLabel(raw);
    case "claimed_type":
      return optionLabel(LINK_TYPE_LABEL, raw);
    case "date_kind":
      return optionLabel(DATE_KIND_LABEL, raw);
    case "frequency":
      return optionLabel(FREQUENCY_LABEL, raw);
    case "deadline":
    case "effective_date":
    case "date":
      return formatDate(raw);
    default:
      return raw;
  }
}

/** The headline of a point on the review screen. */
export function pointHeadline(item: ClaimItem): string {
  const f = item.fields ?? {};
  switch (item.kind) {
    case "OBLIGATION":
      return f.title || f.description || "Requirement";
    case "APPLIES_TO":
      return entityLabel(f.entity);
    case "DATE":
      return `${optionLabel(DATE_KIND_LABEL, f.date_kind)}: ${formatDate(f.date)}`;
    case "LINK":
      return `${optionLabel(LINK_TYPE_LABEL, f.claimed_type)} ${item.link?.target_reference || f.target_hint || "another circular"}`;
    case "PROVISION":
      return [f.number, f.heading].filter(Boolean).join(" ") || f.explanation || "Clause";
    default:
      return f.text || "";
  }
}

/** Lines shown under the headline: the other fields that carry something. */
export function pointDetails(item: ClaimItem): Array<{ label: string; value: string }> {
  const headline = new Set(["title", "text", "entity", "date", "date_kind", "claimed_type", "target_hint"]);
  const out: Array<{ label: string; value: string }> = [];
  for (const spec of FIELDS_OF_KIND[item.kind] ?? []) {
    if (item.kind !== "PROVISION" && headline.has(spec.key)) continue;
    if (item.kind === "PROVISION" && (spec.key === "number" || spec.key === "heading")) continue;
    const v = fieldValueText(spec.key, item.fields?.[spec.key]);
    if (v) out.push({ label: FIELD_LABEL[spec.key] ?? readable(spec.key), value: v });
  }
  return out;
}

/** A short plain line about a point's state, for the review screen. */
export function stateLine(item: ClaimItem): string {
  switch (item.status) {
    case "APPROVED":
      return "Approved";
    case "FIXED":
      return "Corrected and approved";
    case "REJECTED":
      return "Rejected";
    case "PASSED":
      return "Passed its checks";
    default:
      return "";
  }
}

export const REVIEW_TEXT = {
  loading: "Loading the next point...",
  empty: "Nothing needs a decision. New points appear here by themselves (checked every 15 seconds).",
  emptyOptional: "No optional points. New ones appear here by themselves (checked every 15 seconds).",
  saveFailed: "Could not save; try again.",
  conflict: "Someone else already decided this point.",
  loadFailed: "Could not load the points to check. This screen tries again by itself every 15 seconds.",
  alreadyDecided: "That point was already decided.",
  notFound: "That point could not be found.",
} as const;

export const KEY_HELP: Array<{ keys: string; what: string }> = [
  { keys: "A", what: "Approve this point" },
  { keys: "F", what: "Fix it" },
  { keys: "R", what: "Reject it" },
  { keys: "J or right arrow", what: "Skip to the next point" },
  { keys: "K or left arrow", what: "Go back to the one before" },
  { keys: "Ctrl + Enter", what: "Save the fix or the rejection" },
  { keys: "Esc", what: "Close the form or this list" },
  { keys: "?", what: "Show this list" },
];
