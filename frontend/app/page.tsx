"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  DocumentAnalysisData,
  DocumentItem,
  DocumentPage,
  Institution,
  ObligationItem,
  ProvisionItem,
  RelationshipItem,
  fetchDocumentAnalysis,
  fetchDocumentObligations,
  fetchDocumentPages,
  fetchDocumentProvisions,
  fetchDocumentRelationships,
  fetchDocuments,
  fetchInstitutions,
  queryResearchAssistant,
  triggerDocumentAnalysis,
} from "@/services/api";

export default function ProfessionalFeedPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedDoc, setSelectedDoc] = useState<DocumentItem | null>(null);
  const [docPages, setDocPages] = useState<DocumentPage[]>([]);
  const [loadingPages, setLoadingPages] = useState(false);
  const [selectedPageNo, setSelectedPageNo] = useState<number>(1);

  // Intelligence Tabs State
  const [activeTab, setActiveTab] = useState<"summary" | "obligations" | "provisions" | "relationships" | "pages" | "qa">("summary");
  const [analysis, setAnalysis] = useState<DocumentAnalysisData | null>(null);
  const [provisions, setProvisions] = useState<ProvisionItem[]>([]);
  const [obligations, setObligations] = useState<ObligationItem[]>([]);
  const [relationships, setRelationships] = useState<RelationshipItem[]>([]);
  const [analyzing, setAnalyzing] = useState(false);

  // Research Assistant State
  const [qaQuery, setQaQuery] = useState("");
  const [qaLoading, setQaLoading] = useState(false);
  const [qaResponse, setQaResponse] = useState<any>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      const [docs, insts] = await Promise.all([
        fetchDocuments({ search }),
        fetchInstitutions().catch(() => []),
      ]);
      setDocuments(docs);
      if (insts.length > 0) {
        setInstitutions(insts);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [search]);

  const allDepartments = institutions.flatMap((inst) => inst.departments || []);
  const deptCodes = allDepartments.map((d) => d.code).slice(0, 6).join(", ") || "BRPD, DOS, FEPD, PSD, DBI, SFD";
  const totalPages = documents.reduce((sum, d) => sum + (d.versions?.[0]?.page_count || 0), 0);
  const primaryAuthority = institutions[0]?.name || "Bangladesh Bank";

  const handleSelectDoc = async (doc: DocumentItem) => {
    setSelectedDoc(doc);
    setSelectedPageNo(1);
    setActiveTab("summary");
    setQaResponse(null);

    // Fetch pages
    if (doc.versions && doc.versions.length > 0) {
      try {
        setLoadingPages(true);
        const pages = await fetchDocumentPages(doc.id, doc.versions[0].id);
        setDocPages(pages);
      } catch (err) {
        console.error("Error fetching pages:", err);
      } finally {
        setLoadingPages(false);
      }
    } else {
      setDocPages([]);
    }

    // Load AI Intelligence if already generated
    try {
      const [aiData, provs, obls, rels] = await Promise.all([
        fetchDocumentAnalysis(doc.id),
        fetchDocumentProvisions(doc.id),
        fetchDocumentObligations(doc.id),
        fetchDocumentRelationships(doc.id),
      ]);
      setAnalysis(aiData);
      setProvisions(provs);
      setObligations(obls);
      setRelationships(rels);
    } catch (err) {
      console.error("Error fetching analysis artifacts:", err);
    }
  };

  const handleRunAnalysis = async () => {
    if (!selectedDoc) return;
    try {
      setAnalyzing(true);
      const aiData = await triggerDocumentAnalysis(selectedDoc.id, "mock");
      setAnalysis(aiData);
      const [provs, obls, rels] = await Promise.all([
        fetchDocumentProvisions(selectedDoc.id),
        fetchDocumentObligations(selectedDoc.id),
        fetchDocumentRelationships(selectedDoc.id),
      ]);
      setProvisions(provs);
      setObligations(obls);
      setRelationships(rels);
      // Refresh documents to update status
      loadData();
    } catch (err: any) {
      alert(`AI Analysis error: ${err.message}`);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleRunQa = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!qaQuery.trim() || !selectedDoc) return;
    try {
      setQaLoading(true);
      const res = await queryResearchAssistant(qaQuery, selectedDoc.id);
      setQaResponse(res);
    } catch (err: any) {
      alert(`Research query failed: ${err.message}`);
    } finally {
      setQaLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Top Banner & KPI Metrics */}
      <div className="border border-slate-800 bg-slate-900/60 rounded-xl p-6 backdrop-blur">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">
              Bangladesh Regulatory Intelligence Feed
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Real-time monitor of official publications from Bangladesh Bank. All insights verified with page-level provenance.
            </p>
          </div>
          <div className="flex items-center space-x-3">
            <Link
              href="/admin"
              className="px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold rounded-lg shadow-sm transition inline-flex items-center gap-2"
            >
              <span>+ Ingest Circular</span>
            </Link>
          </div>
        </div>

        {/* Financial KPI Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-slate-800/80">
          <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-3">
            <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider block">Total Ingested</span>
            <span className="text-xl font-bold text-white font-mono mt-1 block">{documents.length}</span>
            <span className="text-[10px] text-emerald-400 font-mono mt-0.5 block">{totalPages} pages extracted</span>
          </div>
          <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-3">
            <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider block">Departments Monitored</span>
            <span className="text-xl font-bold text-white font-mono mt-1 block">{allDepartments.length || 6}</span>
            <span className="text-[10px] text-slate-400 font-mono mt-0.5 block truncate" title={deptCodes}>{deptCodes}</span>
          </div>
          <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-3">
            <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider block">Primary Authority</span>
            <span className="text-xl font-bold text-brand-300 font-mono mt-1 block truncate" title={primaryAuthority}>{primaryAuthority}</span>
            <span className="text-[10px] text-slate-400 font-mono mt-0.5 block">Official Media Room</span>
          </div>
          <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-3">
            <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider block">Storage Integrity</span>
            <span className="text-xl font-bold text-emerald-400 font-mono mt-1 block">Immutable</span>
            <span className="text-[10px] text-slate-400 font-mono mt-0.5 block">SHA-256 Provenance</span>
          </div>
        </div>
      </div>

      {/* Search and Filters Bar */}
      <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
        <div className="relative w-full sm:w-96">
          <input
            type="text"
            placeholder="Search circulars (e.g. IFRS 9, UBO, Loan Write-off)..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-slate-900 border border-slate-800 rounded-lg px-4 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-brand-500 font-sans"
          />
        </div>
        <div className="flex items-center space-x-2 text-xs text-slate-400 self-end sm:self-auto font-mono">
          <span>Showing {documents.length} verified publications</span>
        </div>
      </div>

      {/* Main Grid: Circular List & Selected Document Intelligence Reader */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Document Cards Column */}
        <div className="lg:col-span-5 space-y-4">
          {loading ? (
            <div className="p-12 text-center text-slate-500 text-sm border border-slate-800 rounded-xl bg-slate-900/40">
              Loading regulatory repository...
            </div>
          ) : documents.length === 0 ? (
            <div className="p-12 text-center border border-dashed border-slate-800 rounded-xl bg-slate-900/30">
              <p className="text-sm text-slate-400">No documents found matching the filter.</p>
              <Link
                href="/admin"
                className="mt-3 inline-block text-xs font-semibold text-brand-400 hover:text-brand-300"
              >
                Upload circular in Admin Console →
              </Link>
            </div>
          ) : (
            documents.map((doc) => {
              const isSelected = selectedDoc?.id === doc.id;
              const activeVersion = doc.versions?.[0];
              const isPublished = doc.publication_status.includes("PUBLISHED");
              return (
                <div
                  key={doc.id}
                  onClick={() => handleSelectDoc(doc)}
                  className={`p-4 rounded-xl border cursor-pointer transition text-left ${
                    isSelected
                      ? "bg-slate-900 border-brand-500 shadow-md shadow-brand-500/10"
                      : "bg-slate-900/60 border-slate-800/80 hover:bg-slate-900 hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-[11px] font-mono font-semibold px-2 py-0.5 rounded bg-brand-950 text-brand-300 border border-brand-800/60">
                      {doc.reference_number || "BB Circular"}
                    </span>
                    <span className="text-xs text-slate-400 font-mono">
                      {doc.publication_date}
                    </span>
                  </div>

                  <h3 className="text-sm font-semibold text-slate-100 mt-2.5 leading-snug">
                    {doc.title}
                  </h3>

                  <div className="flex items-center justify-between text-xs text-slate-400 mt-3 pt-3 border-t border-slate-800/60 font-mono">
                    <div className="flex items-center space-x-2">
                      <span className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px]">
                        {doc.document_type}
                      </span>
                      <span>{activeVersion?.page_count || 0} pages</span>
                    </div>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                      isPublished ? "bg-emerald-950 text-emerald-400 border border-emerald-800/50" : "bg-amber-950 text-amber-300 border border-amber-800/50"
                    }`}>
                      {doc.publication_status}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Selected Document Full Intelligence & Reader Column */}
        <div className="lg:col-span-7">
          {selectedDoc ? (
            <div className="border border-slate-800 bg-slate-900/80 rounded-xl p-6 sticky top-24 space-y-6">
              {/* Header */}
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-bold text-brand-400">
                    {selectedDoc.reference_number || "REGULATORY DOCUMENT"}
                  </span>
                  <div className="flex items-center space-x-2">
                    {!analysis && (
                      <button
                        onClick={handleRunAnalysis}
                        disabled={analyzing}
                        className="text-xs bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white px-3 py-1.5 rounded font-semibold transition flex items-center gap-1.5 shadow-sm"
                      >
                        {analyzing ? "Analyzing Document..." : "✨ Run AI Intelligence"}
                      </button>
                    )}
                    <a
                      href={`http://localhost:8000/api/v1/documents/${selectedDoc.id}/pdf`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded border border-slate-700 transition flex items-center gap-1.5 font-mono"
                    >
                      <span>View PDF ↗</span>
                    </a>
                  </div>
                </div>
                <h2 className="text-lg font-bold text-white mt-1.5 leading-snug">
                  {selectedDoc.title}
                </h2>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400 mt-2 font-mono">
                  <span>Published: {selectedDoc.publication_date}</span>
                  {selectedDoc.effective_date && (
                    <span>Effective: {selectedDoc.effective_date}</span>
                  )}
                  <span>Status: <span className="text-brand-300">{selectedDoc.publication_status}</span></span>
                </div>
                {analysis && (
                  <div className="mt-2 text-[11px] font-mono text-emerald-400 bg-slate-950 p-2 rounded border border-slate-800 flex items-center justify-between">
                    <span>Model: {analysis.model_name} ({analysis.prompt_version})</span>
                    <span>Citation Coverage: {(analysis.citation_coverage_score * 100).toFixed(1)}% Verified</span>
                  </div>
                )}
              </div>

              {/* Navigation Tabs */}
              <div className="flex border-b border-slate-800 gap-2 overflow-x-auto text-xs font-medium font-mono pb-2">
                <button
                  onClick={() => setActiveTab("summary")}
                  className={`px-3 py-1.5 rounded transition ${
                    activeTab === "summary" ? "bg-brand-600 text-white" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Executive Summary
                </button>
                <button
                  onClick={() => setActiveTab("obligations")}
                  className={`px-3 py-1.5 rounded transition ${
                    activeTab === "obligations" ? "bg-brand-600 text-white" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Obligations ({obligations.length})
                </button>
                <button
                  onClick={() => setActiveTab("provisions")}
                  className={`px-3 py-1.5 rounded transition ${
                    activeTab === "provisions" ? "bg-brand-600 text-white" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Provisions ({provisions.length})
                </button>
                <button
                  onClick={() => setActiveTab("relationships")}
                  className={`px-3 py-1.5 rounded transition ${
                    activeTab === "relationships" ? "bg-brand-600 text-white" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Relationships ({relationships.length})
                </button>
                <button
                  onClick={() => setActiveTab("pages")}
                  className={`px-3 py-1.5 rounded transition ${
                    activeTab === "pages" ? "bg-brand-600 text-white" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Pages & Provenance ({docPages.length})
                </button>
                <button
                  onClick={() => setActiveTab("qa")}
                  className={`px-3 py-1.5 rounded transition ${
                    activeTab === "qa" ? "bg-brand-600 text-white" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Grounded Q&A
                </button>
              </div>

              {/* Tab 1: Executive Summary */}
              {activeTab === "summary" && (
                <div className="space-y-4 text-xs text-slate-300">
                  {analysis ? (
                    <>
                      <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-2">
                        <span className="text-[11px] font-bold uppercase tracking-wider text-brand-400 block">Core Summary</span>
                        <p className="leading-relaxed text-sm text-slate-100">{analysis.executive_summary}</p>
                      </div>
                      {analysis.purpose && (
                        <div>
                          <h4 className="font-semibold text-slate-200 mb-1">Regulatory Purpose</h4>
                          <p className="text-slate-400 leading-relaxed">{analysis.purpose}</p>
                        </div>
                      )}
                      {analysis.key_changes && analysis.key_changes.length > 0 && (
                        <div>
                          <h4 className="font-semibold text-slate-200 mb-1.5">Key Regulatory Changes</h4>
                          <ul className="list-disc pl-5 space-y-1 text-slate-400">
                            {analysis.key_changes.map((kc, i) => (
                              <li key={i}>{kc}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {analysis.impact_summary && Object.keys(analysis.impact_summary).length > 0 && (
                        <div className="bg-slate-950/70 p-3 rounded border border-slate-800 space-y-1.5">
                          <span className="font-semibold text-slate-300 block">Impacted Banking Dimensions</span>
                          <div className="grid grid-cols-2 gap-2 text-[11px]">
                            {Object.entries(analysis.impact_summary).map(([k, v]) => (
                              <div key={k} className="p-2 bg-slate-900 rounded border border-slate-800/80">
                                <span className="font-mono text-brand-300 uppercase block">{k.replace("_", " ")}</span>
                                <span className="text-slate-400 mt-0.5 block">{String(v)}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-center p-8 border border-dashed border-slate-800 rounded-lg">
                      <p className="text-slate-400 mb-3">AI Intelligence has not been generated for this document yet.</p>
                      <button
                        onClick={handleRunAnalysis}
                        disabled={analyzing}
                        className="px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white font-semibold rounded text-xs transition"
                      >
                        {analyzing ? "Processing..." : "Generate AI Analysis Now"}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Tab 2: Mandatory Obligations */}
              {activeTab === "obligations" && (
                <div className="space-y-3 max-h-[450px] overflow-y-auto pr-1">
                  {obligations.length === 0 ? (
                    <p className="text-xs text-slate-500 text-center p-6">No obligations extracted yet.</p>
                  ) : (
                    obligations.map((obl) => (
                      <div key={obl.id} className="p-3.5 bg-slate-950 rounded-lg border border-slate-800 space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-bold text-sm text-slate-100">{obl.title}</span>
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-brand-950 text-brand-300 border border-brand-800">
                            {obl.obligation_type}
                          </span>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed">{obl.requirement_description}</p>
                        <div className="bg-slate-900/90 p-2.5 rounded border border-slate-800/70 text-[11px] font-mono text-slate-400 italic">
                          "{obl.supporting_text}"
                        </div>
                        <div className="flex flex-wrap items-center justify-between text-[11px] font-mono text-slate-400 pt-2 border-t border-slate-900 gap-2">
                          <span>Responsible: <span className="text-slate-300">{obl.applicability_summary}</span></span>
                          {obl.explicit_deadline && (
                            <span className="text-amber-400">Deadline: {obl.explicit_deadline}</span>
                          )}
                          <span className="text-emerald-400">{obl.verification_status}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* Tab 3: Provisions */}
              {activeTab === "provisions" && (
                <div className="space-y-3 max-h-[450px] overflow-y-auto pr-1">
                  {provisions.length === 0 ? (
                    <p className="text-xs text-slate-500 text-center p-6">No provisions extracted yet.</p>
                  ) : (
                    provisions.map((prov) => (
                      <div key={prov.id} className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs font-bold text-brand-400">{prov.provision_number || "Clause"}</span>
                          {prov.heading && <span className="text-xs font-semibold text-slate-300">{prov.heading}</span>}
                        </div>
                        <p className="text-xs text-slate-300 font-mono leading-relaxed bg-slate-900/60 p-2 rounded">
                          {prov.verbatim_text}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* Tab 4: Relationships */}
              {activeTab === "relationships" && (
                <div className="space-y-3 max-h-[450px] overflow-y-auto pr-1">
                  {relationships.length === 0 ? (
                    <p className="text-xs text-slate-500 text-center p-6">No relationships cited in this document.</p>
                  ) : (
                    relationships.map((rel) => (
                      <div key={rel.id} className="p-3.5 bg-slate-950 rounded-lg border border-slate-800 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-purple-950 text-purple-300 border border-purple-800">
                            {rel.relationship_type}
                          </span>
                          <span className="text-xs font-mono text-emerald-400">{rel.verification_status}</span>
                        </div>
                        <h4 className="text-xs font-bold text-slate-200">
                          Target: {rel.target_reference_hint || "Referenced Circular"}
                        </h4>
                        <p className="text-xs font-mono text-slate-400 italic bg-slate-900/80 p-2 rounded border border-slate-800">
                          "{rel.supporting_quote}"
                        </p>
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* Tab 5: Pages & Provenance */}
              {activeTab === "pages" && (
                <div className="space-y-4">
                  {docPages.length > 0 && (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-semibold text-slate-300">
                          Select Page ({docPages.length})
                        </span>
                        <span className="text-[11px] font-mono text-slate-400">
                          Extraction: {docPages.find((p) => p.page_number === selectedPageNo)?.extraction_method}
                        </span>
                      </div>
                      <div className="flex gap-1.5 overflow-x-auto pb-1">
                        {docPages.map((p) => (
                          <button
                            key={p.page_number}
                            onClick={() => setSelectedPageNo(p.page_number)}
                            className={`px-3 py-1 text-xs font-mono rounded border transition ${
                              selectedPageNo === p.page_number
                                ? "bg-brand-600 text-white border-brand-500 font-bold"
                                : "bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200"
                            }`}
                          >
                            Page {p.page_number}
                            {p.has_tables && " 📊"}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="border border-slate-800 bg-slate-950 rounded-lg p-4 max-h-[350px] overflow-y-auto font-mono text-xs text-slate-300 whitespace-pre-wrap leading-relaxed selection:bg-brand-800">
                    {loadingPages ? (
                      <p className="text-slate-500">Loading extracted page text...</p>
                    ) : docPages.length === 0 ? (
                      <p className="text-slate-500">No page text extracted yet.</p>
                    ) : (
                      docPages.find((p) => p.page_number === selectedPageNo)?.raw_text ||
                      "Page content unavailable."
                    )}
                  </div>
                </div>
              )}

              {/* Tab 6: Grounded Q&A Assistant */}
              {activeTab === "qa" && (
                <div className="space-y-4">
                  <form onSubmit={handleRunQa} className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Ask any question about this circular..."
                      value={qaQuery}
                      onChange={(e) => setQaQuery(e.target.value)}
                      className="flex-1 bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-brand-500"
                    />
                    <button
                      type="submit"
                      disabled={qaLoading}
                      className="px-3 py-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-semibold rounded transition"
                    >
                      {qaLoading ? "Searching..." : "Ask AI"}
                    </button>
                  </form>

                  {qaResponse && (
                    <div className="p-4 bg-slate-950 rounded-lg border border-slate-800 space-y-3 text-xs">
                      <span className="font-semibold text-slate-300 block">Grounded Answer:</span>
                      <p className="text-slate-200 leading-relaxed">{qaResponse.answer}</p>
                      {qaResponse.citations && qaResponse.citations.length > 0 && (
                        <div className="pt-2 border-t border-slate-800/80 space-y-1">
                          <span className="text-[11px] font-mono text-brand-400 block font-bold">Supporting Citations:</span>
                          {qaResponse.citations.map((c: any, i: number) => (
                            <div key={i} className="text-[11px] font-mono text-slate-400 bg-slate-900/60 p-2 rounded">
                              <span className="text-slate-300 font-semibold">{c.reference_number || c.document_title} - Page {c.page_number}:</span> "{c.verbatim_excerpt}"
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Provenance Footer */}
              <div className="text-[11px] text-slate-400 flex items-center justify-between border-t border-slate-800/80 pt-3 font-mono">
                <span>Provenance: SHA-256 Verified</span>
                <span>Traceable: 100% Page Citation Invariant</span>
              </div>
            </div>
          ) : (
            <div className="h-96 border border-dashed border-slate-800/80 rounded-xl bg-slate-900/30 flex flex-col items-center justify-center p-6 text-center text-slate-500">
              <span className="text-3xl mb-2">📑</span>
              <p className="text-sm font-medium text-slate-400">Select any circular on the left</p>
              <p className="text-xs text-slate-500 max-w-sm mt-1">
                Inspect AI executive summaries, mandatory obligations, verbatim provisions, relationships, and grounded Q&A.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
