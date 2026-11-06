"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ShieldAlert,
  UploadCloud,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Play,
  Pause,
  ExternalLink,
  FileText,
  Check,
  X,
  Building2,
  Sparkles,
  ArrowLeft,
  Lock,
  Cpu,
  Layers,
  FileSpreadsheet,
} from "lucide-react";
import {
  DocumentItem,
  Institution,
  Source,
  SourceDiscovery,
  approveDiscovery,
  fetchDiscoveries,
  fetchDocuments,
  fetchInstitutions,
  fetchProviderStatus,
  fetchSources,
  rejectDiscovery,
  toggleSourceActive,
  triggerSourceRun,
  uploadDocument,
} from "@/services/api";
import GeminiSetupModal from "@/components/GeminiSetupModal";

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

  // Gemini Setup Modal State
  const [isGeminiModalOpen, setIsGeminiModalOpen] = useState(false);
  const [geminiConfigured, setGeminiConfigured] = useState(false);
  const [activeModel, setActiveModel] = useState("gemini-3.8-flash");

  const loadAllData = async () => {
    try {
      setLoading(true);
      const [insts, docs, srcs, disc, provStatus] = await Promise.all([
        fetchInstitutions(),
        fetchDocuments(),
        fetchSources(),
        fetchDiscoveries(),
        fetchProviderStatus().catch(() => null),
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
      if (provStatus) {
        setGeminiConfigured(provStatus.gemini_api_key_configured);
        setActiveModel(provStatus.default_model);
      }
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
        text: `Success: Ingested "${result.document.title}" (${result.pages_extracted} pages extracted, SHA-256: ${result.version.file_sha256.substring(0, 16)}...)`,
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
          text: `Run completed with restriction: ${run.access_restriction_details?.challenge_type || "Anti-bot challenge"} detected on Bangladesh Bank portal. Automation halted per non-bypass policy.`,
        });
      } else {
        setMonitoringNotice({
          type: "success",
          text: `Monitoring complete: Inspected ${run.pages_inspected} pages, discovered ${run.candidate_links_discovered} candidates (${run.valid_documents_discovered} valid, ${run.duplicate_count} duplicates).`,
        });
      }
      const [refreshedSources, refreshedDisc] = await Promise.all([fetchSources(), fetchDiscoveries()]);
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
      const [refreshedDisc, refreshedDocs] = await Promise.all([fetchDiscoveries(), fetchDocuments()]);
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
      <div className="border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 bg-tealNavy-900/90 dark:bg-tealNavy-900/90 light:bg-white rounded-2xl p-6 shadow-lg transition-colors">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs px-2.5 py-0.5 rounded font-mono font-bold bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-teal-50 text-turquoise dark:text-turquoise light:text-teal-700 border border-tealNavy-700 dark:border-tealNavy-700 light:border-teal-200">
                ADMIN CONSOLE
              </span>
              <span className="text-xs text-slate-400 dark:text-slate-400 light:text-slate-500 font-mono">
                Platform Operator &amp; Ingestion Hub
              </span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white dark:text-white light:text-tealNavy-950 mt-1">
              Source Monitoring &amp; Document Ingestion
            </h1>
            <p className="text-sm text-slate-300 dark:text-slate-300 light:text-slate-600 mt-0.5">
              Live crawler orchestration, Bangladesh Bank WAF telemetry, candidate review queue, and manual PDF dropzone.
            </p>
          </div>
          <div className="flex items-center space-x-3">
            <button
              onClick={() => setIsGeminiModalOpen(true)}
              className="text-xs font-mono font-semibold text-slate-200 dark:text-slate-200 light:text-slate-800 hover:border-turquoise px-3.5 py-2 rounded-lg border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-100 transition flex items-center gap-1.5"
            >
              <Sparkles className="w-3.5 h-3.5 text-turquoise" />
              <span>Gemini Setup</span>
            </button>
            <Link
              href="/"
              className="text-xs font-mono font-semibold text-slate-200 dark:text-slate-200 light:text-slate-800 hover:text-white dark:hover:text-white light:hover:text-tealNavy-950 px-3.5 py-2 rounded-lg border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-100 transition flex items-center gap-1.5"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Professional Feed</span>
            </Link>
          </div>
        </div>
      </div>

      {/* Global Telemetry Alert */}
      {monitoringNotice && (
        <div
          className={`p-4 rounded-xl border text-xs font-mono flex items-center gap-2.5 ${
            monitoringNotice.type === "success"
              ? "bg-emerald-950/80 border-emerald-800 text-emerald-200"
              : monitoringNotice.type === "warning"
              ? "bg-amber-950/80 border-amber-800 text-amber-200"
              : "bg-rose-950/80 border-rose-800 text-rose-200"
          }`}
        >
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span>{monitoringNotice.text}</span>
        </div>
      )}

      {/* AI Intelligence Engine & Operational Health Banner */}
      <div className="border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 bg-tealNavy-900/80 dark:bg-tealNavy-900/80 light:bg-slate-50 rounded-2xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 text-xs font-mono transition-colors">
        <div className="flex items-center gap-3">
          <div className="w-2.5 h-2.5 rounded-full bg-turquoise animate-pulse" />
          <div>
            <span className="text-slate-400 dark:text-slate-400 light:text-slate-500 font-sans font-semibold">
              AI Intelligence Engine:{" "}
            </span>
            <span className="text-slate-200 dark:text-slate-200 light:text-tealNavy-950 font-bold font-mono">
              {geminiConfigured ? `Google Gemini (${activeModel}) - Free Tier Zero Cost` : "Sandbox Mock Engine (Offline Heuristic)"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="px-2.5 py-1 rounded bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-white border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 text-slate-300 dark:text-slate-300 light:text-slate-700 text-[11px]">
            Zero-Cost Policy: <span className="text-turquoise font-bold">ENFORCED</span>
          </span>
          <span className="px-2.5 py-1 rounded bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-white border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 text-slate-300 dark:text-slate-300 light:text-slate-700 text-[11px]">
            Lease Lock: <span className="text-semantic-success font-bold">ACTIVE</span>
          </span>
        </div>
      </div>

      {/* Sources Registry Section */}
      <div className="border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 bg-tealNavy-900/80 dark:bg-tealNavy-900/80 light:bg-white rounded-2xl p-6 space-y-4 shadow-sm transition-colors">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-white dark:text-white light:text-tealNavy-950">
              Registered Regulatory Sources ({sources.length})
            </h2>
            <p className="text-xs text-slate-300 dark:text-slate-300 light:text-slate-600">
              Official institutional portals monitored for publication releases.
            </p>
          </div>
        </div>

        <div className="space-y-3">
          {sources.map((s) => (
            <div
              key={s.id}
              className="p-4 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 bg-tealNavy-950/70 dark:bg-tealNavy-950/70 light:bg-slate-50 flex flex-col md:flex-row md:items-center justify-between gap-4 text-xs transition-colors"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-slate-100 dark:text-slate-100 light:text-tealNavy-950 text-sm">
                    {s.name}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded-full font-mono text-[10px] font-bold border ${
                      s.is_active
                        ? "bg-emerald-950/80 dark:bg-emerald-950/80 light:bg-emerald-100 text-emerald-300 dark:text-emerald-300 light:text-emerald-800 border-emerald-700/80"
                        : "bg-tealNavy-900 text-slate-500 border-tealNavy-700"
                    }`}
                  >
                    {s.is_active ? "ENABLED" : "PAUSED"}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded font-mono text-[10px] font-bold border ${
                      s.access_restriction_status === "CLEAR"
                        ? "bg-tealNavy-900 text-slate-300"
                        : "bg-amber-950/80 dark:bg-amber-950/80 light:bg-amber-100 text-amber-300 dark:text-amber-300 light:text-amber-800 border-amber-600/70"
                    }`}
                  >
                    STATUS: {s.access_restriction_status}
                  </span>
                </div>
                <div className="text-slate-400 dark:text-slate-400 light:text-slate-600 font-mono mt-1 text-[11px] break-all">
                  {s.base_url}
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-slate-400 dark:text-slate-400 light:text-slate-500 font-mono mt-2 text-[10px]">
                  <span>Frequency: Every {s.polling_frequency_minutes}m</span>
                  <span>
                    Last Attempted:{" "}
                    {s.last_attempted_run_at ? new Date(s.last_attempted_run_at).toLocaleString() : "Never"}
                  </span>
                  <span>
                    Last Successful:{" "}
                    {s.last_successful_run_at ? new Date(s.last_successful_run_at).toLocaleString() : "Never"}
                  </span>
                </div>
                {s.last_error && (
                  <div className="text-amber-300 dark:text-amber-300 light:text-amber-800 font-mono text-[10px] mt-2 bg-amber-950/40 dark:bg-amber-950/40 light:bg-amber-50 p-2 rounded-lg border border-amber-700/60 flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 text-amber-400" />
                    <span>Warning: {s.last_error}</span>
                  </div>
                )}
              </div>

              <div className="flex items-center space-x-2 self-start md:self-auto flex-shrink-0">
                <button
                  onClick={() => handleToggleActive(s)}
                  className="px-3 py-1.5 rounded-lg border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white hover:border-turquoise text-slate-300 dark:text-slate-300 light:text-slate-700 text-xs transition font-mono"
                >
                  {s.is_active ? "Pause" : "Enable"}
                </button>
                <button
                  onClick={() => handleTriggerRun(s.id)}
                  disabled={triggeringSourceId === s.id}
                  className="px-4 py-1.5 rounded-lg bg-turquoise hover:bg-turquoise-bright disabled:opacity-50 text-tealNavy-950 font-bold text-xs transition shadow-sm font-mono flex items-center gap-1.5"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${triggeringSourceId === s.id ? "animate-spin" : ""}`} />
                  <span>{triggeringSourceId === s.id ? "Checking..." : "Trigger Run"}</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Discovery Review Queue */}
      <div className="border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 bg-tealNavy-900/80 dark:bg-tealNavy-900/80 light:bg-white rounded-2xl p-6 space-y-4 shadow-sm transition-colors">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-white dark:text-white light:text-tealNavy-950">
              Discovery Review Queue ({discoveries.length})
            </h2>
            <p className="text-xs text-slate-300 dark:text-slate-300 light:text-slate-600">
              Newly identified candidate circulars awaiting editorial approval or verification.
            </p>
          </div>
        </div>

        {discoveries.length === 0 ? (
          <div className="p-8 text-center border border-dashed border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl text-slate-400 text-xs">
            Review queue is clear. No pending candidate publications.
          </div>
        ) : (
          <div className="space-y-2.5 max-h-96 overflow-y-auto">
            {discoveries.map((disc) => (
              <div
                key={disc.id}
                className="p-3.5 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 bg-tealNavy-950/70 dark:bg-tealNavy-950/70 light:bg-slate-50 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-turquoise dark:text-turquoise light:text-teal-700 font-bold text-[11px]">
                      {disc.reference_number || "Reference Unspecified"}
                    </span>
                    {disc.department_code && (
                      <span className="px-1.5 py-0.5 rounded bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-200 text-slate-300 dark:text-slate-300 light:text-slate-700 font-mono text-[10px]">
                        {disc.department_code}
                      </span>
                    )}
                    <span
                      className={`px-1.5 py-0.5 rounded font-mono text-[10px] font-bold ${
                        disc.status === "VALIDATED"
                          ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                          : disc.status === "DUPLICATE"
                          ? "bg-tealNavy-900 text-slate-500"
                          : disc.status === "REJECTED"
                          ? "bg-rose-950 text-rose-400 border border-rose-900"
                          : "bg-tealNavy-850 text-turquoise"
                      }`}
                    >
                      {disc.status}
                    </span>
                  </div>
                  <h4 className="text-slate-200 dark:text-slate-200 light:text-tealNavy-950 font-semibold mt-1">
                    {disc.title || "Bangladesh Bank Publication"}
                  </h4>
                  <div className="text-[10px] text-slate-400 dark:text-slate-400 light:text-slate-500 font-mono mt-1 break-all">
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
                      className="px-2.5 py-1 text-[11px] rounded-lg border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white text-slate-300 hover:text-white transition font-mono flex items-center gap-1"
                    >
                      <span>Source</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                  {disc.status === "VALIDATED" && (
                    <>
                      <button
                        onClick={() => handleApproveDiscovery(disc.id)}
                        className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-lg transition font-mono"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => handleRejectDiscovery(disc.id)}
                        className="px-3 py-1 bg-tealNavy-800 hover:bg-rose-900 text-slate-300 hover:text-rose-200 text-xs font-semibold rounded-lg transition font-mono"
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
        <div className="lg:col-span-6 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 bg-tealNavy-900/80 dark:bg-tealNavy-900/80 light:bg-white rounded-2xl p-6 space-y-6 shadow-sm transition-colors">
          <div>
            <h2 className="text-lg font-bold text-white dark:text-white light:text-tealNavy-950 flex items-center gap-2">
              <UploadCloud className="w-5 h-5 text-turquoise" />
              Manual Ingestion Dropzone
            </h2>
            <p className="text-xs text-slate-300 dark:text-slate-300 light:text-slate-600 mt-1">
              Upload an official circular PDF directly. The system computes SHA-256 hashes, stores immutably in originals namespace, and extracts text page-by-page.
            </p>
          </div>

          {uploadMessage && (
            <div
              className={`p-3.5 rounded-xl text-xs font-mono flex items-center gap-2 ${
                uploadMessage.type === "success"
                  ? "bg-emerald-950/80 border border-emerald-800 text-emerald-300"
                  : "bg-rose-950/80 border border-rose-800 text-rose-300"
              }`}
            >
              {uploadMessage.type === "success" ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <AlertTriangle className="w-4 h-4 text-rose-400" />}
              <span>{uploadMessage.text}</span>
            </div>
          )}

          <form onSubmit={handleUpload} className="space-y-4 text-xs font-sans">
            <div>
              <label className="block text-slate-300 dark:text-slate-300 light:text-tealNavy-950 font-semibold mb-1.5">
                Official PDF File *
              </label>
              <input
                type="file"
                accept=".pdf"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="w-full text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-turquoise file:text-tealNavy-950 hover:file:bg-turquoise-bright cursor-pointer border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl p-2 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-slate-300 dark:text-slate-300 light:text-tealNavy-950 font-semibold mb-1.5">
                  Regulatory Institution *
                </label>
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
                  className="w-full bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl px-3 py-2 text-slate-200 dark:text-slate-200 light:text-tealNavy-950 focus:outline-none focus:border-turquoise"
                >
                  {institutions.map((inst) => (
                    <option key={inst.id} value={inst.id}>
                      {inst.name} ({inst.code})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-300 dark:text-slate-300 light:text-tealNavy-950 font-semibold mb-1.5">
                  Department
                </label>
                <select
                  value={departmentId}
                  onChange={(e) => setDepartmentId(e.target.value)}
                  className="w-full bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl px-3 py-2 text-slate-200 dark:text-slate-200 light:text-tealNavy-950 focus:outline-none focus:border-turquoise"
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
                <label className="block text-slate-300 dark:text-slate-300 light:text-tealNavy-950 font-semibold mb-1.5">
                  Reference Number
                </label>
                <input
                  type="text"
                  placeholder="e.g. SMESPD Circular No. 05/2026"
                  value={refNumber}
                  onChange={(e) => setRefNumber(e.target.value)}
                  className="w-full bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl px-3 py-2 text-slate-200 dark:text-slate-200 light:text-tealNavy-950 focus:outline-none focus:border-turquoise font-mono"
                />
              </div>

              <div>
                <label className="block text-slate-300 dark:text-slate-300 light:text-tealNavy-950 font-semibold mb-1.5">
                  Document Type
                </label>
                <select
                  value={docType}
                  onChange={(e) => setDocType(e.target.value)}
                  className="w-full bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl px-3 py-2 text-slate-200 dark:text-slate-200 light:text-tealNavy-950 focus:outline-none focus:border-turquoise"
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
              <label className="block text-slate-300 dark:text-slate-300 light:text-tealNavy-950 font-semibold mb-1.5">
                Document Title *
              </label>
              <input
                type="text"
                placeholder="Full official circular subject / title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl px-3 py-2 text-slate-200 dark:text-slate-200 light:text-tealNavy-950 focus:outline-none focus:border-turquoise"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-slate-300 dark:text-slate-300 light:text-tealNavy-950 font-semibold mb-1.5">
                  Publication Date *
                </label>
                <input
                  type="date"
                  value={pubDate}
                  onChange={(e) => setPubDate(e.target.value)}
                  className="w-full bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl px-3 py-2 text-slate-200 dark:text-slate-200 light:text-tealNavy-950 focus:outline-none focus:border-turquoise font-mono"
                />
              </div>

              <div>
                <label className="block text-slate-300 dark:text-slate-300 light:text-tealNavy-950 font-semibold mb-1.5">
                  Effective Date
                </label>
                <input
                  type="date"
                  value={effectiveDate}
                  onChange={(e) => setEffectiveDate(e.target.value)}
                  className="w-full bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl px-3 py-2 text-slate-200 dark:text-slate-200 light:text-tealNavy-950 focus:outline-none focus:border-turquoise font-mono"
                />
              </div>
            </div>

            <div>
              <label className="block text-slate-300 dark:text-slate-300 light:text-tealNavy-950 font-semibold mb-1.5">
                Original Source URL (Optional)
              </label>
              <input
                type="url"
                placeholder="https://www.bb.org.bd/mediaroom/circulars/..."
                value={sourceUrl}
                onChange={(e) => setSourceUrl(e.target.value)}
                className="w-full bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl px-3 py-2 text-slate-200 dark:text-slate-200 light:text-tealNavy-950 focus:outline-none focus:border-turquoise font-mono"
              />
            </div>

            <button
              type="submit"
              disabled={uploading}
              className="w-full py-3 bg-turquoise hover:bg-turquoise-bright disabled:opacity-50 text-tealNavy-950 font-bold rounded-xl shadow transition font-sans text-xs tracking-wider uppercase mt-4 flex items-center justify-center gap-2"
            >
              <UploadCloud className="w-4 h-4" />
              <span>{uploading ? "Ingesting & Extracting Pages..." : "Ingest Document & Process"}</span>
            </button>
          </form>
        </div>

        {/* Right Column: Ingested Document Log */}
        <div className="lg:col-span-6 space-y-6">
          <div className="border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 bg-tealNavy-900/80 dark:bg-tealNavy-900/80 light:bg-white rounded-2xl p-6 shadow-sm transition-colors">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-white dark:text-white light:text-tealNavy-950 uppercase tracking-wider font-mono">
                Recent Ingested Publications ({documents.length})
              </h2>
            </div>

            <div className="space-y-2.5 max-h-[580px] overflow-y-auto">
              {documents.length === 0 ? (
                <p className="text-xs text-slate-400 py-4 text-center">No publications in database yet.</p>
              ) : (
                documents.map((d) => (
                  <div
                    key={d.id}
                    className="p-3 rounded-xl border border-tealNavy-700/80 dark:border-tealNavy-700/80 light:border-slate-200 bg-tealNavy-950/70 dark:bg-tealNavy-950/70 light:bg-slate-50 flex items-center justify-between text-xs transition-colors"
                  >
                    <div className="pr-4">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-turquoise dark:text-turquoise light:text-teal-700 font-bold text-[11px]">
                          {d.reference_number || "BB Circular"}
                        </span>
                        <span className="text-[10px] text-slate-400 dark:text-slate-400 light:text-slate-500 font-mono">
                          {d.publication_date}
                        </span>
                      </div>
                      <p className="text-slate-200 dark:text-slate-200 light:text-tealNavy-950 font-medium mt-0.5 line-clamp-1">
                        {d.title}
                      </p>
                      <div className="flex items-center gap-2 mt-1.5">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-mono border ${
                            d.publication_status === "PUBLISHED_HUMAN_REVIEWED"
                              ? "bg-emerald-950 text-emerald-300 border-emerald-800 font-bold"
                              : d.publication_status === "ANALYZING"
                              ? "bg-cyan-950 text-cyan-300 border-cyan-800 animate-pulse font-bold"
                              : d.publication_status === "EXTRACTION_FAILED"
                              ? "bg-rose-950 text-rose-300 border-rose-800 font-bold"
                              : "bg-amber-950 text-amber-300 border-amber-800 font-bold"
                          }`}
                        >
                          {d.publication_status || "DRAFT"}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className="px-2 py-0.5 rounded bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white text-slate-400 font-mono text-[10px] border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300">
                        {d.versions?.[0]?.page_count || 0} pgs
                      </span>
                      <a
                        href={`http://localhost:8000/api/v1/documents/${d.id}/pdf`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[11px] text-turquoise hover:underline font-mono flex items-center gap-0.5"
                      >
                        <span>PDF</span>
                        <ExternalLink className="w-2.5 h-2.5" />
                      </a>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Gemini Zero-Cost Setup Modal */}
      <GeminiSetupModal
        isOpen={isGeminiModalOpen}
        onClose={() => setIsGeminiModalOpen(false)}
        isConfigured={geminiConfigured}
        activeModel={activeModel}
      />
    </div>
  );
}
