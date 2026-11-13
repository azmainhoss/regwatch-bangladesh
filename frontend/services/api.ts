const DEFAULT_DEV_API_URL = "http://localhost:8000/api/v1";

/**
 * Base URL of the FastAPI backend, always ending in /api/v1.
 * Set NEXT_PUBLIC_API_URL at build time for any deployed environment.
 */
export function getApiBaseUrl(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  const raw = envUrl && envUrl.trim().length > 0 ? envUrl.trim() : DEFAULT_DEV_API_URL;
  const clean = raw.replace(/\/+$/, "");
  return clean.endsWith("/api/v1") ? clean : `${clean}/api/v1`;
}

/** Error carrying the HTTP status and the backend's own message. */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Reads FastAPI's `detail` (string or validation list) from an error response. */
async function readErrorMessage(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null);
  const detail = body?.detail ?? body?.message;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((d: any) => {
        const loc = Array.isArray(d?.loc) ? d.loc.filter((x: any) => x !== "body").join(".") : "";
        return loc ? `${loc}: ${d?.msg ?? ""}` : d?.msg ?? JSON.stringify(d);
      })
      .join("; ");
  }
  return `${fallback} (HTTP ${res.status})`;
}

async function throwApiError(res: Response, fallback: string): Promise<never> {
  throw new ApiError(res.status, await readErrorMessage(res, fallback));
}

export const AUTH_CHANGED_EVENT = "regwatch-auth-changed";

/**
 * Calls the backend. Adds the bearer token when the user is signed in.
 * There is no fallback: a failed request is returned or thrown as-is.
 */
export async function apiFetch(endpoint: string, options: RequestInit = {}): Promise<Response> {
  const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const targetUrl = `${getApiBaseUrl()}${cleanEndpoint}`;

  const headers = new Headers(options.headers || {});
  const token = getAuthToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let res: Response;
  try {
    res = await fetch(targetUrl, { ...options, headers });
  } catch {
    throw new ApiError(0, `Cannot reach the RegWatch API at ${getApiBaseUrl()}. Check that the backend is running.`);
  }

  // An expired or invalid token: drop the local session so the UI stops showing signed-in controls.
  if (res.status === 401 && token && !cleanEndpoint.startsWith("/auth/login")) {
    logoutUser();
  }
  return res;
}

export interface Institution {
  id: string;
  code: string;
  name: string;
  name_bn?: string;
  website_url?: string;
  is_active: boolean;
  departments: Array<{
    id: string;
    code: string;
    name: string;
    name_bn?: string;
  }>;
}

export interface DocumentVersion {
  id: string;
  document_id: string;
  version_number: number;
  file_sha256: string;
  file_size_bytes: number;
  page_count: number;
  language: string;
  is_scanned: boolean;
  created_at: string;
}

export interface DocumentPage {
  id: string;
  is_human_corrected?: boolean;
  page_number: number;
  raw_text: string;
  cleaned_text?: string;
  human_corrected_text?: string | null;
  correction_reason?: string | null;
  corrected_by_name?: string | null;
  corrected_at?: string | null;
  extraction_method: string;
  ocr_confidence?: number;
  has_tables: boolean;
  /** SUCCESS_NATIVE, PENDING_VISION, NEEDS_HUMAN_REVIEW, ... */
  quality_status?: string;
  vision_error?: string | null;
  /** One entry per printed line, boxes on a 0-1000 page scale ([ymin, xmin, ymax, xmax]). */
  line_boxes?: LineBox[] | null;
}

/** A box on a 0-1000 page scale: [ymin, xmin, ymax, xmax]. */
export type Box2D = [number, number, number, number];

export interface LineBox {
  text: string;
  box_2d: Box2D;
  /** English text-layer pages also list each word with its own box. */
  words?: Array<{ text: string; box_2d: Box2D }>;
}

/** Where a quote sits on the original page: one box per printed line it covers. */
export interface QuoteBox {
  page_number: number;
  line_index: number;
  box_2d: Box2D;
}

export interface DocumentItem {
  id: string;
  institution_id: string;
  department_id?: string;
  reference_number?: string;
  title: string;
  title_bn?: string;
  document_type: string;
  publication_date: string;
  effective_date?: string;
  source_url?: string;
  current_version_id?: string;
  publication_status: string;
  created_at: string;
  updated_at: string;
  versions: DocumentVersion[];
  is_synthetic?: boolean;
  corpus_type?: string;
  /** Set when this is a private upload; only that user can see it. */
  owner_user_id?: string | null;
  is_private?: boolean;
  /** IN_FORCE, AMENDED, REPLACED or REPEALED, from confirmed links only. */
  in_force_status?: string | null;
  in_force_by_id?: string | null;
  in_force_by_reference?: string | null;
}

export interface Source {
  id: string;
  institution_id: string;
  department_id?: string;
  name: string;
  source_type: string;
  monitoring_method: string;
  base_url: string;
  polling_frequency_minutes: number;
  is_active: boolean;
  last_checked_at?: string;
  last_attempted_run_at?: string;
  last_successful_run_at?: string;
  last_discovered_publication_at?: string;
  last_error?: string;
  access_restriction_status: string;
}

export interface SourceRun {
  id: string;
  source_id: string;
  run_type: string;
  status: string;
  pages_inspected: number;
  candidate_links_discovered: number;
  valid_documents_discovered: number;
  downloads_attempted: number;
  downloads_successful: number;
  duplicate_count: number;
  /** Circulars being added in the background after a "Check now". */
  ingest_queued?: number | null;
  access_restricted: boolean;
  access_restriction_details: Record<string, any>;
  retry_count: number;
  error_count: number;
  error_log?: string;
  started_at: string;
  completed_at?: string;
}

export interface SourceDiscovery {
  id: string;
  source_run_id: string;
  document_id?: string;
  source_url: string;
  file_url?: string;
  title?: string;
  department_code?: string;
  reference_number?: string;
  publication_date?: string;
  discovered_metadata: Record<string, any>;
  rejection_reason?: string;
  status: string;
  created_at: string;
}

/** Matches the backend's UserRead schema (backend/app/modules/identity/schemas.py). */
export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  phone_number?: string | null;
  is_active: boolean;
  is_superuser: boolean;
}

const TOKEN_KEY = "regwatch_token";
const USER_KEY = "regwatch_user";

function notifyAuthChanged() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
  }
}

export function getAuthToken(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem(TOKEN_KEY);
  }
  return null;
}

/**
 * Cached copy of the signed-in user. Only used for first paint; call
 * fetchCurrentUser() to confirm the role with the backend.
 */
export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  if (!localStorage.getItem(TOKEN_KEY)) return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    const u = JSON.parse(raw);
    return u && typeof u === "object" ? (u as AuthUser) : null;
  } catch {
    return null;
  }
}

function storeSession(token: string | null, user: AuthUser | null) {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
  notifyAuthChanged();
}

export function logoutUser() {
  if (typeof window !== "undefined") {
    const hadSession = localStorage.getItem(TOKEN_KEY) !== null || localStorage.getItem(USER_KEY) !== null;
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    if (hadSession) notifyAuthChanged();
  }
}

export async function loginUser(email: string, password: string): Promise<AuthUser> {
  const res = await apiFetch(`/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) await throwApiError(res, "Sign-in failed");
  const data = await res.json();
  const user: AuthUser = data.user;
  storeSession(data.access_token, user);
  return user;
}

export async function registerUser(payload: {
  email: string;
  password: string;
  full_name: string;
  phone_number?: string;
}): Promise<AuthUser> {
  const res = await apiFetch(`/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) await throwApiError(res, "Registration failed");
  const data = await res.json();
  const user: AuthUser = data.user;
  storeSession(data.access_token, user);
  return user;
}

/**
 * Asks the backend who the token belongs to (GET /auth/me) and refreshes the
 * cached user. Returns null and clears the session when the token is missing or rejected.
 */
export async function fetchCurrentUser(): Promise<AuthUser | null> {
  if (!getAuthToken()) return null;
  const res = await apiFetch(`/auth/me`, { cache: "no-store" });
  if (res.status === 401 || res.status === 403) {
    logoutUser();
    return null;
  }
  if (!res.ok) await throwApiError(res, "Could not load the signed-in user");
  const user: AuthUser = await res.json();
  if (typeof window !== "undefined") {
    const before = localStorage.getItem(USER_KEY);
    const after = JSON.stringify(user);
    localStorage.setItem(USER_KEY, after);
    if (before !== after) notifyAuthChanged();
  }
  return user;
}

function getAuthHeaders(): HeadersInit {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function fetchHealth(): Promise<{ status: string; app_name: string; version: string }> {
  const res = await apiFetch(`/health`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "API health check failed");
  return res.json();
}

export interface ProviderStatusInfo {
  service_state?: string;
  is_available?: boolean;
  status: string;
  configured_provider: string;
  default_model: string;
  gemini_api_key_configured: boolean;
  timeout_seconds: number;
  max_retries: number;
  last_checked_at?: string | null;
  admin_diagnostics?: {
    provider_name: string;
    model_identifier: string;
    base_url?: string | null;
    last_checked_at?: string | null;
    last_latency_ms?: number;
    last_status_code?: number;
    last_error?: string | null;
  };
  test_result?: {
    success: boolean;
    busy?: boolean;
    latency_ms?: number;
    error?: string | null;
    message?: string;
  };
}

export async function fetchProviderStatus(): Promise<ProviderStatusInfo> {
  const res = await apiFetch(`/documents/provider-status`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Failed to fetch provider status");
  return res.json();
}

export async function testProviderConnection(): Promise<ProviderStatusInfo> {
  const res = await apiFetch(`/documents/provider-test`, {
    method: "POST",
    headers: { ...getAuthHeaders() },
    cache: "no-store",
  });
  if (!res.ok) await throwApiError(res, "Failed to test provider connection");
  return res.json();
}

export async function fetchInstitutions(): Promise<Institution[]> {
  const res = await apiFetch(`/institutions`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Failed to fetch institutions");
  return res.json();
}

export interface DashboardStats {
  total_documents: number;
  genuine_documents_count: number;
  genuine_pages_count: number;
  synthetic_documents_count: number;
  synthetic_pages_count: number;
  verified_publications_count: number;
  awaiting_review_count: number;
  draft_documents_count: number;
  total_pages_extracted: number;
  departments_monitored_count: number;
  departments_codes: string[];
  primary_authority: string;
  source_monitoring_status: string;
  source_monitoring_message: string;
}

export async function fetchDocumentStats(): Promise<DashboardStats> {
  const res = await apiFetch(`/documents/stats`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Failed to fetch dashboard stats");
  return res.json();
}

export async function fetchDocuments(params?: {
  institution_id?: string;
  search?: string;
  document_type?: string;
  corpus_type?: string;
  publication_status?: string;
}): Promise<DocumentItem[]> {
  const query = new URLSearchParams();
  if (params?.institution_id) query.append("institution_id", params.institution_id);
  if (params?.search) query.append("search", params.search);
  if (params?.document_type) query.append("document_type", params.document_type);
  if (params?.corpus_type) query.append("corpus_type", params.corpus_type);
  if (params?.publication_status) query.append("publication_status", params.publication_status);

  const res = await apiFetch(`/documents?${query.toString()}`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Failed to fetch documents");
  return res.json();
}

export async function fetchDocument(documentId: string): Promise<DocumentItem> {
  const res = await apiFetch(`/documents/${documentId}`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Failed to fetch document");
  return res.json();
}

/** Direct link to the stored original PDF (GET /documents/{id}/pdf). */
export function documentPdfUrl(documentId: string): string {
  return `${getApiBaseUrl()}/documents/${documentId}/pdf`;
}

/**
 * Opens a document's PDF in a new tab. Private documents need the sign-in token,
 * which a plain link cannot send, so the file is fetched first.
 */
export async function openDocumentPdf(documentId: string): Promise<void> {
  const tab = window.open("", "_blank");
  const res = await apiFetch(`/documents/${documentId}/pdf`, { cache: "no-store" });
  if (!res.ok) {
    tab?.close();
    await throwApiError(res, "Could not open the PDF");
  }
  const url = URL.createObjectURL(await res.blob());
  if (tab) tab.location.href = url;
  else window.location.href = url;
}

export interface ReextractResult {
  message: string;
  page_count: number;
  human_corrections_preserved: number;
}

/** Admin only. Re-runs page extraction; pages a person corrected keep their corrected text. */
export async function reextractDocument(documentId: string): Promise<ReextractResult> {
  const res = await apiFetch(`/documents/${documentId}/extract`, { method: "POST" });
  if (!res.ok) await throwApiError(res, "Re-extraction failed");
  return res.json();
}

/**
 * One page of the original PDF as an image (GET .../pages/{n}/image). Fetched with the
 * sign-in token, because private circulars need it, and returned as an object URL.
 */
export async function fetchPageImage(
  documentId: string,
  versionId: string,
  pageNo: number,
  dpi = 144,
  signal?: AbortSignal
): Promise<string> {
  const res = await apiFetch(`/documents/${documentId}/versions/${versionId}/pages/${pageNo}/image?dpi=${dpi}`, { signal });
  if (!res.ok) await throwApiError(res, "Could not load the page image");
  return URL.createObjectURL(await res.blob());
}

export async function fetchDocumentPages(documentId: string, versionId: string): Promise<DocumentPage[]> {
  const res = await apiFetch(`/documents/${documentId}/versions/${versionId}/pages`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Failed to fetch document pages");
  return res.json();
}

export async function uploadDocument(formData: FormData): Promise<any> {
  const headers = getAuthHeaders();
  const res = await apiFetch(`/documents/upload`, {
    method: "POST",
    headers,
    body: formData,
  });
  if (!res.ok) await throwApiError(res, "Upload failed");
  return res.json();
}

export async function fetchSources(): Promise<Source[]> {
  const res = await apiFetch(`/sources`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Failed to fetch sources");
  return res.json();
}

export async function triggerSourceRun(sourceId: string): Promise<SourceRun> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const res = await apiFetch(`/sources/${sourceId}/trigger`, {
    method: "POST",
    headers,
  });
  if (!res.ok) await throwApiError(res, "Failed to trigger source monitoring run");
  return res.json();
}

export interface IngestStatus {
  source_id: string;
  running: boolean;
  total: number;
  done: number;
  successful: number;
  failed: number;
}

export async function fetchIngestStatus(sourceId: string): Promise<IngestStatus> {
  const res = await apiFetch(`/sources/${sourceId}/ingest-status`, { headers: { ...getAuthHeaders() }, cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Could not check the downloads");
  return res.json();
}

export async function toggleSourceActive(sourceId: string, isActive: boolean): Promise<Source> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const res = await apiFetch(`/sources/${sourceId}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify({ is_active: isActive }),
  });
  if (!res.ok) await throwApiError(res, "Failed to toggle source status");
  return res.json();
}

export async function fetchDiscoveries(statusFilter?: string): Promise<SourceDiscovery[]> {
  const query = statusFilter ? `?status_filter=${statusFilter}` : "";
  const res = await apiFetch(`/sources/discoveries${query}`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Failed to fetch discoveries");
  return res.json();
}

export async function approveDiscovery(discoveryId: string): Promise<any> {
  const headers = getAuthHeaders();
  const res = await apiFetch(`/sources/discoveries/${discoveryId}/approve`, {
    method: "POST",
    headers,
  });
  if (!res.ok) await throwApiError(res, "Failed to approve discovery");
  return res.json();
}

export interface SourceStats {
  source_id: string;
  source_name: string;
  is_active: boolean;
  total_discovered: number;
  total_ingested: number;
  total_pending: number;
  total_duplicates: number;
  total_failed: number;
  department_breakdown: Record<string, number>;
  year_breakdown: Record<string, number>;
  language_breakdown: Record<string, number>;
  last_polled_at: string | null;
  last_successful_run_at: string | null;
  access_restriction_status: string;
}

export interface BackfillPayload {
  batch_size: number;
  department?: string;
  year?: number;
  language?: string;
}

export interface BackfillResult {
  status: string;
  message: string;
  attempted: number;
  successful: number;
  duplicates: number;
  failed: number;
  ingested_documents: any[];
}

export async function fetchSourceStats(sourceId: string): Promise<SourceStats> {
  const headers = getAuthHeaders();
  const res = await apiFetch(`/sources/${sourceId}/stats`, { headers, cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Failed to fetch source statistics");
  return res.json();
}

export async function triggerDiscoveryScan(sourceId: string): Promise<SourceRun> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const res = await apiFetch(`/sources/${sourceId}/discover`, {
    method: "POST",
    headers,
  });
  if (!res.ok) await throwApiError(res, "Failed to trigger discovery scan");
  return res.json();
}

export async function triggerBackfillBatch(sourceId: string, payload: BackfillPayload): Promise<BackfillResult> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const res = await apiFetch(`/sources/${sourceId}/backfill`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) await throwApiError(res, "Failed to execute backfill batch");
  return res.json();
}

export async function rejectDiscovery(discoveryId: string, reason: string): Promise<any> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const res = await apiFetch(`/sources/discoveries/${discoveryId}/reject`, {
    method: "POST",
    headers,
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) await throwApiError(res, "Failed to reject discovery");
  return res.json();
}

// Phase 3: AI Intelligence & Extraction Interfaces & APIs

export interface ProvisionItem {
  id: string;
  page_id: string;
  provision_number?: string;
  heading?: string;
  verbatim_text: string;
  order_index: number;
  quote_span_ids?: string[] | null;
  quote_boxes?: QuoteBox[] | null;
}

export interface ObligationItem {
  id: string;
  page_id: string;
  provision_id?: string;
  obligation_type: string;
  title: string;
  requirement_description: string;
  supporting_text: string;
  quote_span_ids?: string[] | null;
  quote_boxes?: QuoteBox[] | null;
  applicability_summary: string;
  explicit_deadline?: string;
  frequency: string;
  verification_status: string;
}

export interface RelationshipItem {
  id: string;
  source_document_id: string;
  target_document_id?: string;
  target_reference_hint?: string;
  relationship_type: string;
  supporting_quote: string;
  quote_span_ids?: string[] | null;
  quote_boxes?: QuoteBox[] | null;
  confidence: number;
  verification_status: string;
}

export interface DocumentAnalysisData {
  id: string;
  document_version_id: string;
  executive_summary: string;
  purpose?: string;
  background?: string;
  key_changes: string[];
  impact_summary: Record<string, any>;
  model_name: string;
  prompt_version: string;
  structured_payload: Record<string, any>;
  citation_coverage_score: number;
  tokens_used: number;
  estimated_cost_usd: number;
  processing_time_ms: number;
  publication_decision: string;
  reviewed_at?: string;
  review_notes?: string;
}

export interface AnalysisJobStatus {
  document_id: string;
  state: "IDLE" | "RUNNING" | "DONE" | "FAILED" | "UNCHANGED" | "WAITING_FOR_PAGES";
  started_at?: string | null;
  finished_at?: string | null;
  message?: string | null;
}

/** Starts the analysis in the background. Answers at once; poll fetchAnalysisStatus until it ends. */
export async function triggerDocumentAnalysis(
  documentId: string,
  opts: { provider?: string; force?: boolean } = {}
): Promise<AnalysisJobStatus> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const payload: Record<string, any> = {};
  if (opts.provider) payload.provider = opts.provider;
  if (opts.force) payload.force = true;
  const res = await apiFetch(`/documents/${documentId}/analyze`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) await throwApiError(res, "Could not start the analysis");
  return res.json();
}

export interface ReadingStatus {
  pages_total: number;
  pages_waiting: number;
  pages_ahead: number;
  minutes_left: number;
  state: "DONE" | "READING" | "QUEUED" | "PAUSED_DAILY_LIMIT" | "PAUSED_NO_KEY" | "PAUSED_NOT_RUNNING";
  resumes_at?: string | null;
  /** What happens after reading: analysed by itself, later (older circulars), or when an admin asks. */
  analysis_after: "AUTOMATIC" | "LATER" | "ON_REQUEST";
}

export async function fetchReadingStatus(documentId: string): Promise<ReadingStatus | null> {
  const res = await apiFetch(`/documents/${documentId}/reading-status`, { headers: { ...getAuthHeaders() }, cache: "no-store" });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchAnalysisStatus(documentId: string): Promise<AnalysisJobStatus> {
  const res = await apiFetch(`/documents/${documentId}/analysis-status`, {
    headers: { ...getAuthHeaders() },
    cache: "no-store",
  });
  if (!res.ok) await throwApiError(res, "Could not check the analysis");
  return res.json();
}

export async function fetchDocumentAnalysis(documentId: string): Promise<DocumentAnalysisData | null> {
  const res = await apiFetch(`/documents/${documentId}/analysis`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) await throwApiError(res, "Failed to fetch document analysis");
  return res.json();
}

export async function fetchDocumentProvisions(documentId: string): Promise<ProvisionItem[]> {
  const res = await apiFetch(`/documents/${documentId}/provisions`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Failed to fetch provisions");
  return res.json();
}

export async function fetchDocumentObligations(documentId: string): Promise<ObligationItem[]> {
  const res = await apiFetch(`/documents/${documentId}/obligations`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Failed to fetch obligations");
  return res.json();
}

export async function fetchDocumentRelationships(documentId: string): Promise<RelationshipItem[]> {
  const res = await apiFetch(`/documents/${documentId}/relationships`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Failed to fetch related circulars");
  return res.json();
}

export async function fetchDocumentExtractionReport(documentId: string, versionId: string): Promise<any> {
  const res = await apiFetch(`/documents/${documentId}/versions/${versionId}/report`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Failed to fetch extraction report");
  return res.json();
}

export async function reviewDocumentAnalysis(
  documentId: string,
  decision: string,
  reviewNotes?: string
): Promise<any> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const res = await apiFetch(`/documents/${documentId}/publish`, {
    method: "POST",
    headers,
    body: JSON.stringify({ decision, review_notes: reviewNotes }),
  });
  if (!res.ok) await throwApiError(res, "Failed to submit review");
  return res.json();
}

export async function submitPageCorrection(
  documentId: string,
  versionId: string,
  pageNo: number,
  correctedText: string,
  notes?: string
): Promise<{ message: string; page: DocumentPage }> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const res = await apiFetch(`/documents/${documentId}/versions/${versionId}/pages/${pageNo}/correct`, {
    method: "POST",
    headers,
    body: JSON.stringify({ corrected_text: correctedText, correction_notes: notes }),
  });
  if (!res.ok) await throwApiError(res, "Failed to submit correction");
  return res.json();
}

export interface ResearchCitation {
  document_title: string;
  reference_number?: string | null;
  page_number: number;
  verbatim_excerpt: string;
  document_id?: string | null;
  version_id?: string | null;
  sentence_ids?: string[];
  quote_boxes?: QuoteBox[] | Array<Record<string, unknown>>;
}

export interface ResearchAnswer {
  query: string;
  answer: string;
  is_grounded: boolean;
  citations: ResearchCitation[];
  caveats: string[];
}

export async function queryResearchAssistant(query: string, documentId?: string): Promise<ResearchAnswer> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const res = await apiFetch(`/research/query`, {
    method: "POST",
    headers,
    body: JSON.stringify({ query, document_id: documentId }),
  });
  if (res.status === 401) {
    throw new ApiError(401, "Please sign in to ask questions.");
  }
  if (!res.ok) await throwApiError(res, "Research query failed");
  return res.json();
}

/** The sentences that best match a question, exact from the page. Local search only: instant. */
export async function fetchResearchMatches(query: string, documentId?: string): Promise<ResearchCitation[]> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const res = await apiFetch(`/research/matches`, {
    method: "POST",
    headers,
    body: JSON.stringify({ query, document_id: documentId }),
  });
  if (!res.ok) return [];
  const data = await res.json();
  return Array.isArray(data?.matches) ? data.matches : [];
}

export interface SearchSnippet {
  page_number: number;
  version_id: string;
  language: string;
  text: string;
  /** [start, end) of each search word inside `text`, in UTF-16 units. */
  matches: Array<[number, number]>;
  starts_mid_text: boolean;
  ends_mid_text: boolean;
}

export interface SearchHit {
  document_id: string;
  reference_number?: string | null;
  title: string;
  title_bn?: string | null;
  publication_date: string;
  publication_status: string;
  document_type: string;
  department_code?: string | null;
  current_version_id?: string | null;
  is_private: boolean;
  title_match: boolean;
  matching_pages: number;
  snippets: SearchSnippet[];
}

export interface SearchResponse {
  query: string;
  terms: string[];
  total: number;
  limit: number;
  offset: number;
  results: SearchHit[];
}

export interface SearchParams {
  q: string;
  department?: string;
  year_from?: string;
  year_to?: string;
  doc_type?: string;
  status?: string;
  limit?: number;
  offset?: number;
}

export async function searchCirculars(params: SearchParams, signal?: AbortSignal): Promise<SearchResponse> {
  const query = new URLSearchParams();
  (Object.keys(params) as Array<keyof SearchParams>).forEach((k) => {
    const v = params[k];
    if (v !== undefined && v !== "" && v !== null) query.append(k, String(v));
  });
  const res = await apiFetch(`/documents/search?${query.toString()}`, { cache: "no-store", signal });
  if (!res.ok) await throwApiError(res, "Search failed");
  return res.json();
}


// ---------------------------------------------------------------------------------------------
// Links between circulars: in-force status, history, graph, admin review, compare
// ---------------------------------------------------------------------------------------------

export type InForceStatus = "IN_FORCE" | "AMENDED" | "REPLACED" | "REPEALED";

export interface DocumentRef {
  id: string;
  reference_number?: string | null;
  title: string;
  publication_date?: string | null;
  current_version_id?: string | null;
  is_private: boolean;
  in_force_status?: string | null;
}

/** One relationship with the exact quote and page that support it. */
export interface RelLink {
  id: string;
  relationship_type: string;
  /** PENDING_REVIEW links never change a circular's in-force status. */
  verification_status: "PENDING_REVIEW" | "VERIFIED" | "REJECTED" | string;
  confidence: number;
  detection_method?: string | null;
  supporting_quote: string;
  page_number?: number | null;
  source_version_id?: string | null;
  quote_boxes?: QuoteBox[] | null;
  source: DocumentRef;
  target?: DocumentRef | null;
  target_reference_hint?: string | null;
  reviewed_at?: string | null;
}

export interface RelStatus {
  document_id: string;
  in_force_status: string;
  in_force_by?: DocumentRef | null;
  current_version?: DocumentRef | null;
  chain_has_cycle: boolean;
  verified_incoming: RelLink[];
  unconfirmed_incoming: RelLink[];
  outgoing: RelLink[];
}

export interface RelGraphNode {
  key: string;
  document_id?: string | null;
  reference_number?: string | null;
  title: string;
  publication_date?: string | null;
  in_force_status?: string | null;
  in_library: boolean;
  is_private: boolean;
  is_center: boolean;
  current_version_id?: string | null;
}

export interface RelGraphEdge {
  id: string;
  source: string;
  target: string;
  relationship_type: string;
  verification_status: string;
  supporting_quote: string;
  page_number?: number | null;
  source_version_id?: string | null;
  source_document_id: string;
  target_document_id?: string | null;
  target_reference_hint?: string | null;
  confidence: number;
}

export interface RelGraph {
  document_id: string;
  depth: number;
  nodes: RelGraphNode[];
  edges: RelGraphEdge[];
  truncated: boolean;
}

export interface RelTimelineItem {
  document: DocumentRef;
  is_selected: boolean;
  is_current: boolean;
  changes: RelLink[];
}

export interface RelTimeline {
  document_id: string;
  in_force_status: string;
  in_force_by?: DocumentRef | null;
  current_version?: DocumentRef | null;
  chain_has_cycle: boolean;
  has_unconfirmed: boolean;
  items: RelTimelineItem[];
}

export interface PendingLinks {
  total: number;
  limit: number;
  offset: number;
  links: RelLink[];
}

export interface ReviewResult {
  link: RelLink;
  source_in_force_status?: string | null;
  target_in_force_status?: string | null;
}

export async function fetchRelStatus(documentId: string): Promise<RelStatus> {
  const res = await apiFetch(`/relationships/document/${documentId}/status`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Could not load the in-force status");
  return res.json();
}

export async function fetchRelGraph(documentId: string, depth = 2): Promise<RelGraph> {
  const res = await apiFetch(`/relationships/document/${documentId}/graph?depth=${depth}`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Could not load the relationship graph");
  return res.json();
}

export async function fetchRelTimeline(documentId: string): Promise<RelTimeline> {
  const res = await apiFetch(`/relationships/document/${documentId}/timeline`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Could not load the history");
  return res.json();
}

/** Admin only. */
export async function fetchPendingLinks(limit = 100): Promise<PendingLinks> {
  const res = await apiFetch(`/relationships/pending?limit=${limit}`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "Could not load the links awaiting review");
  return res.json();
}

/** Admin only. VERIFIED confirms a link (it then counts for the in-force status); REJECTED drops it. */
export async function reviewRelationship(relationshipId: string, decision: "VERIFIED" | "REJECTED"): Promise<ReviewResult> {
  const res = await apiFetch(`/relationships/${relationshipId}/review`, {
    method: "POST",
    headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  });
  if (!res.ok) await throwApiError(res, "Could not save that decision");
  return res.json();
}

/** Admin only. Looks again for the stored circular each unlinked reference names. */
export async function relinkRelationships(): Promise<{ linked: number; still_unlinked: number; message: string }> {
  const res = await apiFetch(`/relationships/relink`, { method: "POST", headers: getAuthHeaders() });
  if (!res.ok) await throwApiError(res, "Could not look for link targets");
  return res.json();
}

export interface CompareSide {
  version_id: string;
  document_id: string;
  reference_number?: string | null;
  title: string;
  version_number: number;
  language: string;
  page_count: number;
  pages_compared: number;
}

export interface CompareWord {
  op: "equal" | "insert" | "delete";
  text: string;
}

export interface CompareOp {
  op: "equal" | "insert" | "delete" | "replace";
  left_text?: string | null;
  right_text?: string | null;
  left_page?: number | null;
  right_page?: number | null;
  words: CompareWord[];
}

export interface CompareResult {
  left: CompareSide;
  right: CompareSide;
  truncated: boolean;
  stats: { equal: number; insert: number; delete: number; replace: number };
  ops: CompareOp[];
}

export async function compareVersions(leftVersionId: string, rightVersionId: string, signal?: AbortSignal): Promise<CompareResult> {
  const res = await apiFetch(`/documents/compare?left=${leftVersionId}&right=${rightVersionId}`, { cache: "no-store", signal });
  if (!res.ok) await throwApiError(res, "Could not compare these files");
  return res.json();
}
