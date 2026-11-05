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
  const res = await fetch(`${API_BASE_URL}/documents/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Upload failed");
  }
  return res.json();
}
