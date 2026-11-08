import seedData from "@/data/seed.json";

export interface DocumentFilterParams {
  institution_id?: string;
  department_id?: string;
  document_type?: string;
  search?: string;
  publication_status?: string;
  corpus_type?: string;
  limit?: number;
  offset?: number;
}

export function getInstitutions() {
  const depts = seedData.institution_departments || [];
  const insts = (seedData.institutions || []).map((inst: any) => ({
    ...inst,
    is_active: Boolean(inst.is_active),
    departments: depts.filter((d: any) => d.institution_id === inst.id),
  }));
  return insts;
}

export function getDocuments(params: DocumentFilterParams = {}) {
  let docs = [...(seedData.documents || [])];

  // Map versions into each document
  const versions = seedData.document_versions || [];
  docs = docs.map((d: any) => {
    const docVersions = versions.filter((v: any) => v.document_id === d.id);
    return {
      ...d,
      is_synthetic: false,
      corpus_type: "GENUINE",
      versions: docVersions,
    };
  });

  // Filter
  if (params.department_id) {
    docs = docs.filter((d: any) => d.department_id === params.department_id);
  }
  if (params.institution_id) {
    docs = docs.filter((d: any) => d.institution_id === params.institution_id);
  }
  if (params.document_type) {
    docs = docs.filter((d: any) => d.document_type === params.document_type);
  }
  if (params.publication_status) {
    docs = docs.filter((d: any) => d.publication_status === params.publication_status);
  }
  if (params.search) {
    const s = params.search.toLowerCase();
    docs = docs.filter(
      (d: any) =>
        (d.title && d.title.toLowerCase().includes(s)) ||
        (d.reference_number && d.reference_number.toLowerCase().includes(s))
    );
  }

  // Sort by publication_date desc
  docs.sort((a: any, b: any) => {
    const dateA = new Date(a.publication_date).getTime();
    const dateB = new Date(b.publication_date).getTime();
    return dateB - dateA;
  });

  const offset = params.offset || 0;
  const limit = params.limit || 50;
  return docs.slice(offset, offset + limit);
}

export function getDocument(id: string) {
  const doc = (seedData.documents || []).find((d: any) => d.id === id);
  if (!doc) return null;
  const versions = (seedData.document_versions || []).filter((v: any) => v.document_id === doc.id);
  return {
    ...doc,
    is_synthetic: false,
    corpus_type: "GENUINE",
    versions,
  };
}

export function getDocumentAnalysis(documentId: string) {
  const doc = (seedData.documents || []).find((d: any) => d.id === documentId);
  if (!doc) return null;
  const versions = (seedData.document_versions || []).filter((v: any) => v.document_id === doc.id);
  const versionIds = versions.map((v: any) => v.id);

  // Find analysis matching any version
  const analysis = (seedData.document_analyses || []).find((a: any) =>
    versionIds.includes(a.document_version_id)
  );
  if (!analysis) return null;

  // Safe parsing helper for SQLite text/json fields
  const parseJson = (val: any, fallback: any) => {
    if (typeof val === "string") {
      try {
        return JSON.parse(val);
      } catch {
        return fallback;
      }
    }
    return val ?? fallback;
  };

  const keyChanges = parseJson(analysis.key_changes, []);
  const impactSummary = parseJson(analysis.impact_summary, {});
  const structuredPayload = parseJson(analysis.structured_payload, {});
  const validationErrors = parseJson(analysis.validation_errors, []);

  // Find claims and citations
  const claims = (seedData.analysis_claims || []).filter((c: any) => c.analysis_id === analysis.id);
  const enrichedClaims = claims.map((c: any) => {
    const citations = (seedData.claim_citations || []).filter((cit: any) => cit.claim_id === c.id);
    return {
      ...c,
      citations,
    };
  });

  return {
    ...analysis,
    key_changes: Array.isArray(keyChanges) ? keyChanges : [keyChanges].filter(Boolean),
    impact_summary: typeof impactSummary === "object" ? impactSummary : {},
    structured_payload: typeof structuredPayload === "object" ? structuredPayload : {},
    validation_errors: Array.isArray(validationErrors) ? validationErrors : [],
    claims: enrichedClaims,
  };
}

export function getDocumentPages(documentId: string, versionId: string) {
  const pages = (seedData.document_pages || []).filter(
    (p: any) => p.document_version_id === versionId
  );
  pages.sort((a: any, b: any) => a.page_number - b.page_number);
  return pages;
}

export function getDocumentProvisions(documentId: string) {
  const doc = (seedData.documents || []).find((d: any) => d.id === documentId);
  if (!doc) return [];
  const versions = (seedData.document_versions || []).filter((v: any) => v.document_id === doc.id);
  const versionIds = versions.map((v: any) => v.id);
  return (seedData.provisions || []).filter((p: any) => versionIds.includes(p.document_version_id));
}

export function getDocumentObligations(documentId: string) {
  const doc = (seedData.documents || []).find((d: any) => d.id === documentId);
  if (!doc) return [];
  const versions = (seedData.document_versions || []).filter((v: any) => v.document_id === doc.id);
  const versionIds = versions.map((v: any) => v.id);
  return (seedData.obligations || []).filter((o: any) => versionIds.includes(o.document_version_id));
}

export function getDocumentStats() {
  const docs = seedData.documents || [];
  const versions = seedData.document_versions || [];
  const totalPages = versions.reduce((sum: number, v: any) => sum + (v.page_count || 0), 0);
  const depts = (seedData.institution_departments || []).map((d: any) => d.code);
  const uniqueDepts = Array.from(new Set(depts.filter(Boolean))).sort();

  return {
    total_documents: docs.length,
    genuine_documents_count: docs.length,
    synthetic_fixtures_count: 0,
    verified_publications_count: docs.filter((d: any) => (d.publication_status || "").startsWith("PUBLISHED")).length,
    awaiting_review_count: docs.filter((d: any) => d.publication_status === "AWAITING_REVIEW").length,
    draft_documents_count: 0,
    total_pages_extracted: totalPages,
    departments_monitored_count: uniqueDepts.length,
    departments_codes: uniqueDepts,
    primary_authority: "Bangladesh Bank",
    source_monitoring_status: "ACTIVE",
    source_monitoring_message: "Automated Bangladesh Bank continuous publication monitoring active.",
  };
}

export function getSources() {
  return seedData.sources || [];
}

export function updateSource(id: string, updates: Partial<any>) {
  const source = (seedData.sources || []).find((s: any) => s.id === id);
  if (source) {
    Object.assign(source, updates);
    return source;
  }
  return null;
}

export function getDocumentCitationsWithPages(documentId: string) {
  const doc = (seedData.documents || []).find((d: any) => d.id === documentId);
  if (!doc) return [];
  const versions = (seedData.document_versions || []).filter((v: any) => v.document_id === doc.id);
  const versionIds = versions.map((v: any) => v.id);
  const analyses = (seedData.document_analyses || []).filter((a: any) => versionIds.includes(a.document_version_id));
  const analysisIds = analyses.map((a: any) => a.id);

  const claims = (seedData.analysis_claims || []).filter((c: any) => analysisIds.includes(c.analysis_id));
  const claimMap = new Map(claims.map((c: any) => [c.id, c.statement]));

  const pageMap = new Map((seedData.document_pages || []).map((p: any) => [p.id, p.page_number]));

  const citations = (seedData.claim_citations || []).filter((cit: any) => claimMap.has(cit.claim_id));

  return citations.map((cit: any) => {
    const pageNum = pageMap.get(cit.page_id) || 1;
    const stmt = claimMap.get(cit.claim_id) || "";
    const quote = cit.quoted_text || stmt;
    return {
      document_id: documentId,
      document_title: doc.title,
      reference_number: doc.reference_number,
      page_number: pageNum,
      claim_statement: stmt,
      verbatim_excerpt: quote,
      quoted_text: quote,
      quote: quote,
    };
  });
}

export function authenticate(username: string, pass: string) {
  const cleanUsername = username.toLowerCase().trim();
  const u = (seedData.users || []).find(
    (x: any) =>
      x.email.toLowerCase() === cleanUsername ||
      (cleanUsername === "cco@nationalbank.bd" && x.email === "cco@abcbank.bd") ||
      (cleanUsername === "cco@abcbank.bd" && x.email === "cco@abcbank.bd")
  );
  if (u) {
    return {
      access_token: `mock_jwt_token_${u.id}`,
      token_type: "bearer",
      user: {
        id: u.id,
        email: u.email,
        full_name: u.full_name,
        is_superuser: Boolean(u.is_superuser),
        is_active: Boolean(u.is_active),
        organization_name: Boolean(u.is_superuser) ? "RegWatch Bangladesh" : "ABC Bank PLC",
        designation: Boolean(u.is_superuser) ? "System Administrator" : "Chief Compliance Officer",
      },
    };
  }
  // Default fallback user for demo
  return {
    access_token: "mock_jwt_token_demo_banker",
    token_type: "bearer",
    user: {
      id: "demo-banker-id",
      email: username || "compliance@abcbank.bd",
      full_name: "Mahmudur Rahman, CCO",
      is_superuser: username.includes("admin"),
      is_active: true,
      organization_name: username.includes("admin") ? "RegWatch Bangladesh" : "ABC Bank PLC",
      designation: username.includes("admin") ? "System Administrator" : "Chief Compliance Officer",
    },
  };
}

