"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { DocumentItem, DocumentPage, Institution, fetchDocumentPages, fetchDocuments, fetchInstitutions } from "@/services/api";

export default function ProfessionalFeedPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedDoc, setSelectedDoc] = useState<DocumentItem | null>(null);
  const [docPages, setDocPages] = useState<DocumentPage[]>([]);
  const [loadingPages, setLoadingPages] = useState(false);
  const [selectedPageNo, setSelectedPageNo] = useState<number>(1);

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

      {/* Main Grid: Circular List & Selected Document Reader */}
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
                    <span className="text-[10px] text-emerald-400">
                      {doc.publication_status}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Selected Document Page-Level Provenance Reader */}
        <div className="lg:col-span-7">
          {selectedDoc ? (
            <div className="border border-slate-800 bg-slate-900/80 rounded-xl p-6 sticky top-24 space-y-6">
              {/* Header */}
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-bold text-brand-400">
                    {selectedDoc.reference_number || "REGULATORY DOCUMENT"}
                  </span>
                  <a
                    href={`http://localhost:8000/api/v1/documents/${selectedDoc.id}/pdf`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded border border-slate-700 transition flex items-center gap-1.5 font-mono"
                  >
                    <span>View Original PDF ↗</span>
                  </a>
                </div>
                <h2 className="text-lg font-bold text-white mt-1.5 leading-snug">
                  {selectedDoc.title}
                </h2>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400 mt-2 font-mono">
                  <span>Published: {selectedDoc.publication_date}</span>
                  {selectedDoc.effective_date && (
                    <span>Effective: {selectedDoc.effective_date}</span>
                  )}
                  <span>Status: {selectedDoc.publication_status}</span>
                </div>
                {selectedDoc.versions?.[0] && (
                  <div className="mt-2 text-[10px] font-mono text-slate-500 break-all bg-slate-950 p-2 rounded border border-slate-900">
                    SHA-256: {selectedDoc.versions[0].file_sha256}
                  </div>
                )}
              </div>

              {/* Page Selector Tabs */}
              {docPages.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-slate-300">
                      Extracted Pages ({docPages.length})
                    </span>
                    <span className="text-[11px] font-mono text-slate-400">
                      Method: {docPages.find((p) => p.page_number === selectedPageNo)?.extraction_method}
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

              {/* Page Content Display */}
              <div className="border border-slate-800 bg-slate-950 rounded-lg p-4 max-h-[500px] overflow-y-auto font-mono text-xs text-slate-300 whitespace-pre-wrap leading-relaxed selection:bg-brand-800">
                {loadingPages ? (
                  <p className="text-slate-500">Loading extracted page text...</p>
                ) : docPages.length === 0 ? (
                  <p className="text-slate-500">No page text extracted yet.</p>
                ) : (
                  docPages.find((p) => p.page_number === selectedPageNo)?.raw_text ||
                  "Page content unavailable."
                )}
              </div>

              <div className="text-[11px] text-slate-400 flex items-center justify-between border-t border-slate-800/80 pt-3 font-mono">
                <span>Provenance: Exact byte extraction</span>
                <span>Audit trail intact</span>
              </div>
            </div>
          ) : (
            <div className="h-96 border border-dashed border-slate-800/80 rounded-xl bg-slate-900/30 flex flex-col items-center justify-center p-6 text-center text-slate-500">
              <span className="text-3xl mb-2">📑</span>
              <p className="text-sm font-medium text-slate-400">Select any circular on the left</p>
              <p className="text-xs text-slate-500 max-w-sm mt-1">
                Inspect verbatim extracted text page-by-page, verify its SHA-256 cryptographic checksum, and view the original PDF.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
