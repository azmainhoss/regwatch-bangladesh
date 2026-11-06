const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

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
  page_number: number;
  raw_text: string;
  cleaned_text?: string;
  extraction_method: string;
  ocr_confidence?: number;
  has_tables: boolean;
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

// Helper to get auth token
function getAuthToken(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem("regwatch_token");
  }
  return null;
}

function getAuthHeaders(): HeadersInit {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function fetchHealth(): Promise<{ status: string; app_name: string; version: string }> {
  const res = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error("API health check failed");
  return res.json();
}

export interface ProviderStatusInfo {
  configured_provider: string;
  default_model: string;
  gemini_api_key_configured: boolean;
  status: string;
  timeout_seconds: number;
  max_retries: number;
  billing_policy: string;
}

export async function fetchProviderStatus(): Promise<ProviderStatusInfo> {
  const res = await fetch(`${API_BASE_URL}/documents/provider-status`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch provider status");
  return res.json();
}

export async function fetchInstitutions(): Promise<Institution[]> {
  const res = await fetch(`${API_BASE_URL}/institutions`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch institutions");
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
  const res = await fetch(`${API_BASE_URL}/documents/stats`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch dashboard stats");
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

  const res = await fetch(`${API_BASE_URL}/documents?${query.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch documents");
  return res.json();
}

export async function fetchDocumentPages(documentId: string, versionId: string): Promise<DocumentPage[]> {
  const res = await fetch(`${API_BASE_URL}/documents/${documentId}/versions/${versionId}/pages`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch document pages");
  return res.json();
}

export async function uploadDocument(formData: FormData): Promise<any> {
  const headers = getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/documents/upload`, {
    method: "POST",
    headers,
    body: formData,
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Upload failed");
  }
  return res.json();
}

export async function fetchSources(): Promise<Source[]> {
  const res = await fetch(`${API_BASE_URL}/sources`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch sources");
  return res.json();
}

export async function triggerSourceRun(sourceId: string): Promise<SourceRun> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const res = await fetch(`${API_BASE_URL}/sources/${sourceId}/trigger`, {
    method: "POST",
    headers,
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to trigger source monitoring run");
  }
  return res.json();
}

export async function toggleSourceActive(sourceId: string, isActive: boolean): Promise<Source> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const res = await fetch(`${API_BASE_URL}/sources/${sourceId}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify({ is_active: isActive }),
  });
  if (!res.ok) throw new Error("Failed to toggle source status");
  return res.json();
}

export async function fetchDiscoveries(statusFilter?: string): Promise<SourceDiscovery[]> {
  const query = statusFilter ? `?status_filter=${statusFilter}` : "";
  const res = await fetch(`${API_BASE_URL}/sources/discoveries${query}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch discoveries");
  return res.json();
}

export async function approveDiscovery(discoveryId: string): Promise<any> {
  const headers = getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/sources/discoveries/${discoveryId}/approve`, {
    method: "POST",
    headers,
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to approve discovery");
  }
  return res.json();
}

export async function rejectDiscovery(discoveryId: string, reason: string): Promise<any> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const res = await fetch(`${API_BASE_URL}/sources/discoveries/${discoveryId}/reject`, {
    method: "POST",
    headers,
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to reject discovery");
  }
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
}

export interface ObligationItem {
  id: string;
  page_id: string;
  provision_id?: string;
  obligation_type: string;
  title: string;
  requirement_description: string;
  supporting_text: string;
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

export async function triggerDocumentAnalysis(documentId: string, provider: string = "mock"): Promise<DocumentAnalysisData> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const res = await fetch(`${API_BASE_URL}/documents/${documentId}/analyze`, {
    method: "POST",
    headers,
    body: JSON.stringify({ provider }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to run AI analysis");
  }
  return res.json();
}

export async function fetchDocumentAnalysis(documentId: string): Promise<DocumentAnalysisData | null> {
  const res = await fetch(`${API_BASE_URL}/documents/${documentId}/analysis`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Failed to fetch document analysis");
  return res.json();
}

export async function fetchDocumentProvisions(documentId: string): Promise<ProvisionItem[]> {
  const res = await fetch(`${API_BASE_URL}/documents/${documentId}/provisions`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchDocumentObligations(documentId: string): Promise<ObligationItem[]> {
  const res = await fetch(`${API_BASE_URL}/documents/${documentId}/obligations`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchDocumentRelationships(documentId: string): Promise<RelationshipItem[]> {
  const res = await fetch(`${API_BASE_URL}/documents/${documentId}/relationships`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchDocumentExtractionReport(documentId: string, versionId: string): Promise<any> {
  const res = await fetch(`${API_BASE_URL}/documents/${documentId}/versions/${versionId}/report`, { cache: "no-store" });
  if (!res.ok) return null;
  return res.json();
}

export async function reviewDocumentAnalysis(
  documentId: string,
  decision: string,
  reviewNotes?: string
): Promise<any> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const res = await fetch(`${API_BASE_URL}/documents/${documentId}/publish`, {
    method: "POST",
    headers,
    body: JSON.stringify({ decision, review_notes: reviewNotes }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to submit review");
  }
  return res.json();
}

export async function submitPageCorrection(
  documentId: string,
  versionId: string,
  pageNo: number,
  correctedText: string,
  notes?: string
): Promise<any> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const res = await fetch(`${API_BASE_URL}/documents/${documentId}/versions/${versionId}/pages/${pageNo}/correct`, {
    method: "POST",
    headers,
    body: JSON.stringify({ corrected_text: correctedText, correction_notes: notes }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to submit correction");
  }
  return res.json();
}

export async function queryResearchAssistant(query: string, documentId?: string): Promise<{
  query: string;
  answer: string;
  is_grounded: boolean;
  citations: Array<{ document_title: string; reference_number?: string; page_number: number; verbatim_excerpt: string }>;
}> {
  const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
  const res = await fetch(`${API_BASE_URL}/research/query`, {
    method: "POST",
    headers,
    body: JSON.stringify({ query, document_id: documentId }),
  });
  if (!res.ok) {
    if (res.status === 401) {
      throw new Error("Authentication required: Please log in or provide valid credentials to query the research assistant.");
    }
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Research query failed");
  }
  return res.json();
}
