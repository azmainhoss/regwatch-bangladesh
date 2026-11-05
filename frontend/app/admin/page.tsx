"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  DocumentItem,
  Institution,
  Source,
  SourceDiscovery,
  approveDiscovery,
  fetchDiscoveries,
  fetchDocuments,
  fetchInstitutions,
  fetchSources,
  rejectDiscovery,
  toggleSourceActive,
  triggerSourceRun,
  uploadDocument
} from "@/services/api";

export default function AdminConsolePage() {
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [discoveries, setDiscoveries] = useState<SourceDiscovery[]>([]);
  const [loading, setLoading] = useState(true);

  // Upload Form State
  const [file, setFile] = useState<File | null>(null);
  const [institutionId, setInstitutionId] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [refNumber, setRefNumber] = useState("");
  const [title, setTitle] = useState("");
  const [docType, setDocType] = useState("CIRCULAR");
  const [pubDate, setPubDate] = useState(new Date().toISOString().split("T")[0]);
  const [effectiveDate, setEffectiveDate] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Source Monitoring Trigger State
  const [triggeringSourceId, setTriggeringSourceId] = useState<string | null>(null);
  const [monitoringNotice, setMonitoringNotice] = useState<{ type: "success" | "warning" | "error"; text: string } | null>(null);

  const loadAllData = async () => {
    try {
      setLoading(true);
      const [insts, docs, srcs, disc] = await Promise.all([
        fetchInstitutions(),
        fetchDocuments(),
        fetchSources(),
        fetchDiscoveries()
      ]);
      setInstitutions(insts);
      if (insts.length > 0) {
        setInstitutionId(insts[0].id);
        if (insts[0].departments.length > 0) {
          setDepartmentId(insts[0].departments[0].id);
        }
      }
      setDocuments(docs);
      setSources(srcs);
      setDiscoveries(disc);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAllData();
  }, []);

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setUploadMessage({ type: "error", text: "Please select an official PDF file." });
      return;
    }
    if (!institutionId || !title || !pubDate) {
      setUploadMessage({ type: "error", text: "Institution, Title, and Publication Date are required." });
      return;
    }

    try {
      setUploading(true);
      setUploadMessage(null);

      const formData = new FormData();
      formData.append("file", file);
      formData.append("institution_id", institutionId);
      if (departmentId) formData.append("department_id", departmentId);
      if (refNumber) formData.append("reference_number", refNumber);
      formData.append("title", title);
      formData.append("document_type", docType);
      formData.append("publication_date", pubDate);
      if (effectiveDate) formData.append("effective_date", effectiveDate);
      if (sourceUrl) formData.append("source_url", sourceUrl);

      const result = await uploadDocument(formData);
      setUploadMessage({
        type: "success",
        text: `Success! Ingested "${result.document.title}" (${result.pages_extracted} pages extracted, SHA-256: ${result.version.file_sha256.substring(0, 16)}...)`
      });

      // Reset form
      setFile(null);
      setRefNumber("");
      setTitle("");
      setSourceUrl("");
      const refreshedDocs = await fetchDocuments();
      setDocuments(refreshedDocs);
    } catch (err: any) {
      setUploadMessage({ type: "error", text: err.message || "Failed to upload document" });
    } finally {
      setUploading(false);
    }
  };

  const handleTriggerRun = async (sourceId: string) => {
    try {
      setTriggeringSourceId(sourceId);
      setMonitoringNotice(null);
      const run = await triggerSourceRun(sourceId);
      if (run.access_restricted) {
        setMonitoringNotice({
          type: "warning",
          text: `Run completed with restriction: ${run.access_restriction_details?.challenge_type || "Anti-bot challenge"} detected on Bangladesh Bank portal. Automation halted per non-bypass policy.`
        });
      } else {
        setMonitoringNotice({
          type: "success",
          text: `Monitoring complete: Inspected ${run.pages_inspected} pages, discovered ${run.candidate_links_discovered} candidates (${run.valid_documents_discovered} valid, ${run.duplicate_count} duplicates).`
        });
      }
      // Refresh sources and discoveries
      const [refreshedSources, refreshedDisc] = await Promise.all([
        fetchSources(),
        fetchDiscoveries()
      ]);
      setSources(refreshedSources);
      setDiscoveries(refreshedDisc);
    } catch (err: any) {
      setMonitoringNotice({ type: "error", text: err.message || "Run failed" });
    } finally {
      setTriggeringSourceId(null);
    }
  };

  const handleToggleActive = async (source: Source) => {
    try {
      await toggleSourceActive(source.id, !source.is_active);
      const refreshed = await fetchSources();
      setSources(refreshed);
    } catch (err: any) {
      alert("Failed to toggle source status: " + err.message);
    }
  };

  const handleApproveDiscovery = async (discoveryId: string) => {
    try {
      await approveDiscovery(discoveryId);
      alert("Discovery approved and queued for ingestion!");
      const [refreshedDisc, refreshedDocs] = await Promise.all([
        fetchDiscoveries(),
        fetchDocuments()
      ]);
      setDiscoveries(refreshedDisc);
      setDocuments(refreshedDocs);
    } catch (err: any) {
      alert("Approval error: " + err.message);
    }
  };

  const handleRejectDiscovery = async (discoveryId: string) => {
    const reason = prompt("Enter reason for rejecting this candidate publication:");
    if (!reason) return;
    try {
      await rejectDiscovery(discoveryId, reason);
      const refreshedDisc = await fetchDiscoveries();
      setDiscoveries(refreshedDisc);
    } catch (err: any) {
      alert("Rejection error: " + err.message);
    }
  };

  const selectedInst = institutions.find((i) => i.id === institutionId);

  return (
    <div className="space-y-8">
      {/* Admin Header */}
      <div className="border border-slate-800 bg-slate-900/60 rounded-xl p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs px-2 py-0.5 rounded bg-brand-900/80 text-brand-300 font-mono border border-brand-700/50">
                ADMIN CONSOLE
              </span>
              <span className="text-xs text-slate-500 font-mono">Platform Operator & Ingestion Hub</span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white mt-1">
              Source Monitoring & Document Ingestion
            </h1>
            <p className="text-sm text-slate-400 mt-0.5">
              Live crawler orchestration, WAF restriction telemetry, candidate review queue, and manual dropzone.
            </p>
          </div>
          <Link
            href="/"
            className="text-xs font-mono text-slate-400 hover:text-white px-3 py-1.5 rounded border border-slate-800 bg-slate-950 transition self-start sm:self-auto"
          >
            ← Back to Professional Feed
          </Link>
        </div>
      </div>

      {/* Global Telemetry Alert */}
      {monitoringNotice && (
        <div
          className={`p-4 rounded-xl border text-xs font-mono ${
            monitoringNotice.type === "success"
              ? "bg-emerald-950/80 border-emerald-800 text-emerald-200"
              : monitoringNotice.type === "warning"
              ? "bg-amber-950/80 border-amber-800 text-amber-200"
              : "bg-rose-950/80 border-rose-800 text-rose-200"
          }`}
        >
          {monitoringNotice.text}
        </div>
      )}

      {/* Sources Registry Section */}
      <div className="border border-slate-800 bg-slate-900/40 rounded-xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-white">Registered Regulatory Sources ({sources.length})</h2>
            <p className="text-xs text-slate-400">Official institutional portals monitored for publication releases.</p>
          </div>
        </div>

        <div className="space-y-3">
          {sources.map((s) => (
            <div
              key={s.id}
              className="p-4 rounded-xl border border-slate-800 bg-slate-950 flex flex-col md:flex-row md:items-center justify-between gap-4 text-xs"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-200 text-sm">{s.name}</span>
                  <span
                    className={`px-2 py-0.5 rounded-full font-mono text-[10px] border ${
                      s.is_active
                        ? "bg-emerald-950 text-emerald-400 border-emerald-800"
                        : "bg-slate-900 text-slate-500 border-slate-800"
                    }`}
                  >
                    {s.is_active ? "ENABLED" : "PAUSED"}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded font-mono text-[10px] ${
                      s.access_restriction_status === "CLEAR"
                        ? "bg-slate-900 text-slate-300"
                        : "bg-amber-950 text-amber-400 border border-amber-800"
                    }`}
                  >
                    STATUS: {s.access_restriction_status}
                  </span>
                </div>
                <div className="text-slate-400 font-mono mt-1 text-[11px] break-all">{s.base_url}</div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-slate-500 font-mono mt-2 text-[10px]">
                  <span>Frequency: Every {s.polling_frequency_minutes}m</span>
                  <span>Last Attempted: {s.last_attempted_run_at ? new Date(s.last_attempted_run_at).toLocaleString() : "Never"}</span>
                  <span>Last Successful: {s.last_successful_run_at ? new Date(s.last_successful_run_at).toLocaleString() : "Never"}</span>
                </div>
                {s.last_error && (
                  <div className="text-amber-400/90 font-mono text-[10px] mt-1.5 bg-amber-950/40 p-1.5 rounded border border-amber-900/50">
                    Warning: {s.last_error}
                  </div>
                )}
              </div>

              <div className="flex items-center space-x-2 self-start md:self-auto flex-shrink-0">
                <button
                  onClick={() => handleToggleActive(s)}
                  className="px-3 py-1.5 rounded border border-slate-700 bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs transition font-mono"
                >
                  {s.is_active ? "Pause" : "Enable"}
                </button>
                <button
                  onClick={() => handleTriggerRun(s.id)}
                  disabled={triggeringSourceId === s.id}
                  className="px-4 py-1.5 rounded bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white font-semibold text-xs transition shadow-sm font-mono"
                >
                  {triggeringSourceId === s.id ? "Checking..." : "Trigger Run Now"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Discovery Review Queue */}
      <div className="border border-slate-800 bg-slate-900/40 rounded-xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-white">Discovery Review Queue ({discoveries.length})</h2>
            <p className="text-xs text-slate-400">Newly identified candidate circulars awaiting editorial approval or verification.</p>
          </div>
        </div>

        {discoveries.length === 0 ? (
          <div className="p-8 text-center border border-dashed border-slate-800 rounded-lg text-slate-500 text-xs">
            Review queue is clear. No pending candidate publications.
          </div>
        ) : (
          <div className="space-y-2.5 max-h-96 overflow-y-auto">
            {discoveries.map((disc) => (
              <div
                key={disc.id}
                className="p-3.5 rounded-lg border border-slate-800 bg-slate-950 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-brand-400 font-semibold text-[11px]">
                      {disc.reference_number || "Reference Unspecified"}
                    </span>
                    {disc.department_code && (
                      <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono text-[10px]">
                        {disc.department_code}
                      </span>
                    )}
                    <span
                      className={`px-1.5 py-0.5 rounded font-mono text-[10px] ${
                        disc.status === "VALIDATED"
                          ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                          : disc.status === "DUPLICATE"
                          ? "bg-slate-900 text-slate-500"
                          : disc.status === "REJECTED"
                          ? "bg-rose-950 text-rose-400 border border-rose-900"
                          : "bg-brand-950 text-brand-300"
                      }`}
                    >
                      {disc.status}
                    </span>
                  </div>
                  <h4 className="text-slate-200 font-medium mt-1">{disc.title || "Bangladesh Bank Publication"}</h4>
                  <div className="text-[10px] text-slate-500 font-mono mt-1 break-all">
                    Link: {disc.file_url || disc.source_url}
                  </div>
                  {disc.rejection_reason && (
                    <div className="text-rose-400 text-[10px] font-mono mt-1">Reason: {disc.rejection_reason}</div>
                  )}
                </div>

                <div className="flex items-center space-x-2 flex-shrink-0 self-start md:self-auto">
                  {disc.file_url && (
                    <a
                      href={disc.file_url}
                      target="_blank"
                      rel="noreferrer"
                      className="px-2.5 py-1 text-[11px] rounded border border-slate-800 bg-slate-900 text-slate-400 hover:text-white transition font-mono"
                    >
                      Source ↗
                    </a>
                  )}
                  {disc.status === "VALIDATED" && (
                    <>
                      <button
                        onClick={() => handleApproveDiscovery(disc.id)}
                        className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded transition font-mono"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => handleRejectDiscovery(disc.id)}
                        className="px-3 py-1 bg-slate-800 hover:bg-rose-900 text-slate-300 hover:text-rose-200 text-xs font-medium rounded transition font-mono"
                      >
                        Reject
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Manual Dropzone & Repository Column */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Column: Official PDF Dropzone Form */}
        <div className="lg:col-span-6 border border-slate-800 bg-slate-900/40 rounded-xl p-6 space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-white">Manual Ingestion Dropzone</h2>
            <p className="text-xs text-slate-400 mt-1">
              Upload an official circular PDF directly. The system computes SHA-256 hashes, stores immutably in originals namespace, and extracts text page-by-page.
            </p>
          </div>

          {uploadMessage && (
            <div
              className={`p-3 rounded-lg text-xs font-mono ${
                uploadMessage.type === "success"
                  ? "bg-emerald-950/80 border border-emerald-800 text-emerald-300"
                  : "bg-rose-950/80 border border-rose-800 text-rose-300"
              }`}
            >
              {uploadMessage.text}
            </div>
          )}

          <form onSubmit={handleUpload} className="space-y-4 text-xs font-sans">
            <div>
              <label className="block text-slate-300 font-medium mb-1.5">Official PDF File *</label>
              <input
                type="file"
                accept=".pdf"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="w-full text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-brand-600 file:text-white hover:file:bg-brand-500 cursor-pointer border border-slate-800 rounded-lg p-2 bg-slate-950"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-slate-300 font-medium mb-1.5">Regulatory Institution *</label>
                <select
                  value={institutionId}
                  onChange={(e) => {
                    setInstitutionId(e.target.value);
                    const inst = institutions.find((i) => i.id === e.target.value);
                    if (inst && inst.departments.length > 0) {
                      setDepartmentId(inst.departments[0].id);
                    } else {
                      setDepartmentId("");
                    }
                  }}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500"
                >
                  {institutions.map((inst) => (
                    <option key={inst.id} value={inst.id}>
                      {inst.name} ({inst.code})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1.5">Department</label>
                <select
                  value={departmentId}
                  onChange={(e) => setDepartmentId(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500"
                >
                  <option value="">-- Unspecified --</option>
                  {selectedInst?.departments.map((dept) => (
                    <option key={dept.id} value={dept.id}>
                      {dept.code} - {dept.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-slate-300 font-medium mb-1.5">Reference Number</label>
                <input
                  type="text"
                  placeholder="e.g. BRPD Circular No. 15/2024"
                  value={refNumber}
                  onChange={(e) => setRefNumber(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1.5">Document Type</label>
                <select
                  value={docType}
                  onChange={(e) => setDocType(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500"
                >
                  <option value="CIRCULAR">CIRCULAR</option>
                  <option value="CIRCULAR_LETTER">CIRCULAR_LETTER</option>
                  <option value="GUIDELINE">GUIDELINE</option>
                  <option value="NOTIFICATION">NOTIFICATION</option>
                  <option value="POLICY">POLICY</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1.5">Document Title *</label>
              <input
                type="text"
                placeholder="Full official circular subject / title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-slate-300 font-medium mb-1.5">Publication Date *</label>
                <input
                  type="date"
                  value={pubDate}
                  onChange={(e) => setPubDate(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1.5">Effective Date</label>
                <input
                  type="date"
                  value={effectiveDate}
                  onChange={(e) => setEffectiveDate(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500 font-mono"
                />
              </div>
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1.5">Original Source URL (Optional)</label>
              <input
                type="url"
                placeholder="https://www.bb.org.bd/mediaroom/circulars/..."
                value={sourceUrl}
                onChange={(e) => setSourceUrl(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500 font-mono"
              />
            </div>

            <button
              type="submit"
              disabled={uploading}
              className="w-full py-2.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white font-semibold rounded-lg shadow transition font-sans text-xs tracking-wide uppercase mt-4"
            >
              {uploading ? "Ingesting & Extracting Pages..." : "Ingest Document & Process"}
            </button>
          </form>
        </div>

        {/* Right Column: Ingested Document Log */}
        <div className="lg:col-span-6 space-y-6">
          <div className="border border-slate-800 bg-slate-900/40 rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-white uppercase tracking-wider font-mono">
                Recent Ingested Publications ({documents.length})
              </h2>
            </div>

            <div className="space-y-2.5 max-h-[580px] overflow-y-auto">
              {documents.length === 0 ? (
                <p className="text-xs text-slate-500 py-4 text-center">No publications in database yet.</p>
              ) : (
                documents.map((d) => (
                  <div
                    key={d.id}
                    className="p-3 rounded-lg border border-slate-800/80 bg-slate-950 flex items-center justify-between text-xs"
                  >
                    <div className="pr-4">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-brand-400 font-semibold text-[11px]">
                          {d.reference_number || "BB Circular"}
                        </span>
                        <span className="text-[10px] text-slate-500 font-mono">
                          {d.publication_date}
                        </span>
                      </div>
                      <p className="text-slate-300 font-medium mt-0.5 line-clamp-1">{d.title}</p>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className="px-2 py-0.5 rounded bg-slate-900 text-slate-400 font-mono text-[10px] border border-slate-800">
                        {d.versions?.[0]?.page_count || 0} pgs
                      </span>
                      <a
                        href={`http://localhost:8000/api/v1/documents/${d.id}/pdf`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[11px] text-brand-400 hover:text-brand-300 font-mono"
                      >
                        PDF ↗
                      </a>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
