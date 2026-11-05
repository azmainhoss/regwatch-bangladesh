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

export async function fetchInstitutions(): Promise<Institution[]> {
  const res = await fetch(`${API_BASE_URL}/institutions`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch institutions");
  return res.json();
}

export async function fetchDocuments(params?: {
  institution_id?: string;
  search?: string;
  document_type?: string;
}): Promise<DocumentItem[]> {
  const query = new URLSearchParams();
  if (params?.institution_id) query.append("institution_id", params.institution_id);
  if (params?.search) query.append("search", params.search);
  if (params?.document_type) query.append("document_type", params.document_type);

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
