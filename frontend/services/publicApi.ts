import { serverApi } from "./serverApi";

/** Server-side reads of the public (no sign-in) circular API, used by the search-engine pages. */

export interface HubLink {
  code: string;
  name: string;
  total: number;
  analysed: number;
}
export interface Hubs {
  departments: HubLink[];
  topics: HubLink[];
  years: HubLink[];
  total: number;
  analysed: number;
}
export interface ListItem {
  path: string;
  reference_number?: string | null;
  title: string;
  title_bn?: string | null;
  department: string;
  publication_date?: string | null;
  analysed: boolean;
  topics: string[];
}
export interface CircularList {
  kind: "dept" | "topic" | "year" | "latest";
  code: string;
  name: string;
  name_bn?: string | null;
  total: number;
  analysed: number;
  items: ListItem[];
  indexable: boolean;
}

async function get<T>(path: string, revalidate = 600): Promise<T | null> {
  const res = await fetch(serverApi(path), { next: { revalidate } }).catch(() => null);
  if (!res || res.status === 404) return null;
  if (!res.ok) throw new Error(`Could not load ${path} (${res.status})`);
  return res.json();
}

export const getHubs = () => get<Hubs>("/public/hubs");
export const getList = (kind: string, code: string) =>
  get<CircularList>(`/public/lists/${encodeURIComponent(kind)}/${encodeURIComponent(code)}`);
export const getRelated = (id: string) => get<ListItem[]>(`/public/related/${encodeURIComponent(id)}`);
export const getTopicsOf = (id: string) => get<HubLink[]>(`/public/topics-of/${encodeURIComponent(id)}`);

export function longDate(value?: string | null) {
  if (!value) return "";
  const d = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(d.getTime())
    ? value
    : d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
}

/** "BRPD Circular No. 23/2026" style label: the reference plus the year when the reference has none. */
export function refLabel(ref: string | null | undefined, date?: string | null) {
  if (!ref) return "";
  if (/(19|20)\d{2}/.test(ref) || !date) return ref;
  return `${ref}/${date.slice(0, 4)}`;
}

const BN_DIGITS = "০১২৩৪৫৬৭৮৯";
const BN_DEPT: Record<string, string> = {
  BRPD: "বিআরপিডি",
  FEPD: "এফইপিডি",
  FEOD: "এফইওডি",
  DOS: "ডিওএস",
  DFIM: "ডিএফআইএম",
  PSD: "পিএসডি",
  SFD: "এসএফডি",
  BFIU: "বিএফআইইউ",
  SMESPD: "এসএমইএসপিডি",
  ACD: "এসিডি",
  DCM: "ডিসিএম",
  DMD: "ডিএমডি",
  MPD: "এমপিডি",
  FE: "এফই",
};
const toBnDigits = (s: string) => s.replace(/[0-9]/g, (d) => BN_DIGITS[Number(d)]);

/** "বিআরপিডি সার্কুলার নং ১৫/২০২৪": how Bangla readers search for a circular. Empty when the reference is unclear. */
export function bnRef(ref: string | null | undefined, date?: string | null) {
  if (!ref) return "";
  const m = ref.match(/^([A-Za-z.&]+)(?:-\d+)?\s+Circular(\s+Letter)?\s+No\.?\s*(\d+)(?:\s*[/-]\s*((?:19|20)\d{2}))?/i);
  if (!m) return "";
  const dept = BN_DEPT[m[1].replace(/\./g, "").toUpperCase()];
  if (!dept) return "";
  const year = m[4] || date?.slice(0, 4) || "";
  return `${dept} সার্কুলার${m[2] ? " লেটার" : ""} নং ${toBnDigits(m[3])}${year ? `/${toBnDigits(year)}` : ""}`;
}

export const bnDeptName = (code: string) => BN_DEPT[code.toUpperCase()] || "";
export const bnYear = (y: string) => toBnDigits(y);
