"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowUpRight, Check, ExternalLink, FileText, Lock, Pause, Play, RefreshCw, Sparkles, UploadCloud, X } from "lucide-react";
import {
  ApiError,
  AuthUser,
  AUTH_CHANGED_EVENT,
  DocumentItem,
  Institution,
  ProviderStatusInfo,
  Source,
  SourceDiscovery,
  SourceStats,
  approveDiscovery,
  documentPdfUrl,
  openDocumentPdf,
  fetchCurrentUser,
  fetchDiscoveries,
  fetchDocuments,
  fetchInstitutions,
  fetchProviderStatus,
  fetchSources,
  fetchSourceStats,
  getStoredUser,
  rejectDiscovery,
  testProviderConnection,
  toggleSourceActive,
  triggerBackfillBatch,
  triggerDiscoveryScan,
  triggerSourceRun,
  uploadDocument,
} from "@/services/api";
import GeminiSetupModal from "@/components/GeminiSetupModal";
import AccountModal from "@/components/AccountModal";
import StatusBadge, { PrivateTag, Tag } from "@/components/StatusBadge";
import { EASE_OUT, EmptyState, Notice, SkeletonLine, titleWithoutRef } from "@/components/ui";

type TabId = "queue" | "collection" | "upload" | "library" | "engine";
type NoticeState = { type: "success" | "warning" | "error"; text: string; status?: string } | null;

function when(value?: string) {
  if (!value) return "Never";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function Stat({ label, value, note, tone }: { label: string; value: React.ReactNode; note?: string; tone?: "warn" | "ok" }) {
  return (
    <div className="min-w-0">
      <dt className="text-[13px] text-ink-3">{label}</dt>
      <dd className={`mt-0.5 truncate text-[22px] font-semibold tabular-nums ${tone === "warn" ? "text-warn" : tone === "ok" ? "text-ok" : "text-ink"}`}>{value}</dd>
      {note && <dd className="text-[12.5px] text-ink-3">{note}</dd>}
    </div>
  );
}

function PanelHeading({ title, children, actions }: { title: string; children?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3 border-b border-line px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h2 className="text-[17px] font-semibold text-ink">{title}</h2>
        {children && <p className="mt-0.5 max-w-prose text-[14px] text-ink-3">{children}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export default function AdminConsolePage() {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [isAccountModalOpen, setIsAccountModalOpen] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [discoveries, setDiscoveries] = useState<SourceDiscovery[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<TabId>("queue");
  const [queueFilter, setQueueFilter] = useState<"open" | "all">("open");
  const [approvingId, setApprovingId] = useState<string | null>(null);

  // Upload form
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [institutionId, setInstitutionId] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [refNumber, setRefNumber] = useState("");
  const [title, setTitle] = useState("");
  const [docType, setDocType] = useState("CIRCULAR");
  const [pubDate, setPubDate] = useState(new Date().toISOString().split("T")[0]);
  const [effectiveDate, setEffectiveDate] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [visibility, setVisibility] = useState<"shared" | "private">("shared");
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Source checks
  const [triggeringSourceId, setTriggeringSourceId] = useState<string | null>(null);
  const [monitoringNotice, setMonitoringNotice] = useState<NoticeState>(null);

  // Collection and backfill
  const [sourceStats, setSourceStats] = useState<SourceStats | null>(null);
  const [backfillLoading, setBackfillLoading] = useState(false);
  const [backfillDept, setBackfillDept] = useState("");
  const [backfillResultNotice, setBackfillResultNotice] = useState<string | null>(null);
  const [discoveryLoading, setDiscoveryLoading] = useState(false);

  // AI provider
  const [isGeminiModalOpen, setIsGeminiModalOpen] = useState(false);
  const [geminiConfigured, setGeminiConfigured] = useState(false);
  const [activeModel, setActiveModel] = useState("gemini-flash-lite-latest");
  const [providerInfo, setProviderInfo] = useState<ProviderStatusInfo | null>(null);
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionTestFeedback, setConnectionTestFeedback] = useState<{ success: boolean; message: string } | null>(null);

  // Confirm the role with the backend (GET /auth/me) instead of trusting the cached copy.
  const verifyUser = async () => {
    try {
      const user = await fetchCurrentUser();
      setCurrentUser(user);
      if (user?.is_superuser) {
        loadAllData();
      }
    } catch (err: any) {
      setCurrentUser(null);
      setLoadError(err.message || "Could not verify your account with the backend.");
    } finally {
      setCheckingAuth(false);
    }
  };

  useEffect(() => {
    verifyUser();
    const onAuthChanged = () => setCurrentUser(getStoredUser());
    window.addEventListener(AUTH_CHANGED_EVENT, onAuthChanged);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, onAuthChanged);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadAllData = async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const [insts, docs, srcs, disc, provStatus] = await Promise.all([
        fetchInstitutions(),
        fetchDocuments(),
        fetchSources(),
        fetchDiscoveries(),
        fetchProviderStatus(),
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
      if (srcs.length > 0) {
        try {
          const stats = await fetchSourceStats(srcs[0].id);
          setSourceStats(stats);
        } catch (e) {
          console.error("Could not fetch source stats", e);
        }
      }
      setDiscoveries(disc);
      setProviderInfo(provStatus);
      setGeminiConfigured(provStatus.gemini_api_key_configured);
      setActiveModel(provStatus.default_model);
    } catch (err: any) {
      console.error(err);
      setLoadError(err.message || "Failed to load data from the backend.");
    } finally {
      setLoading(false);
    }
  };

  const handleTestProviderConnection = async () => {
    try {
      setTestingConnection(true);
      setConnectionTestFeedback(null);
      const res = await testProviderConnection();
      setProviderInfo(res);
      // The backend answers 200 even when the probe fails; the outcome is in test_result.
      const ok = res.test_result?.success === true;
      setConnectionTestFeedback({
        success: ok,
        message: ok
          ? `Connection works. Latency ${res.test_result?.latency_ms ?? "unknown"} ms, service state "${res.service_state || res.status}".`
          : `Connection failed: ${res.test_result?.error || "the provider did not respond successfully"}.`,
      });
    } catch (err: any) {
      setConnectionTestFeedback({ success: false, message: `Connection test failed: ${err.message}` });
    } finally {
      setTestingConnection(false);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setUploadMessage({ type: "error", text: "Please select an official PDF file." });
      return;
    }
    if (!institutionId || !title || !pubDate) {
      setUploadMessage({ type: "error", text: "Institution, title and publication date are required." });
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
      formData.append("visibility", visibility);

      const result = await uploadDocument(formData);
      setUploadMessage({
        type: "success",
        text: `Added "${result.document.title}": ${result.pages_extracted} pages extracted, SHA-256 ${result.version.file_sha256.substring(0, 16)}...`,
      });

      setFile(null);
      setFileKey((k) => k + 1);
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
          status: run.status,
          text: `The website blocked the check (${run.access_restriction_details?.challenge_type || "anti-bot challenge"}). Checks stop here; RegWatch does not try to get around blocks.`,
        });
      } else {
        setMonitoringNotice({
          type: run.status === "FAILED" ? "error" : run.status === "FAILED_RETRY" ? "warning" : "success",
          status: run.status,
          text: `Looked at ${run.pages_inspected ?? 0} pages and found ${run.candidate_links_discovered ?? 0} links: ${run.valid_documents_discovered ?? 0} new, ${run.duplicate_count ?? 0} already known.${run.error_log ? ` Errors: ${run.error_log}` : ""}`,
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
      setMonitoringNotice({ type: "error", text: "Failed to change source status: " + err.message });
    }
  };

  const handleRunDiscoveryScan = async (sourceId: string) => {
    try {
      setDiscoveryLoading(true);
      const run = await triggerDiscoveryScan(sourceId);
      setMonitoringNotice({
        type: run.status === "FAILED" || run.status === "FAILED_RETRY" || run.access_restricted ? "warning" : "success",
        status: run.status,
        text: `Archive scan found ${run.candidate_links_discovered ?? 0} publications: ${run.valid_documents_discovered ?? 0} new candidates, ${run.duplicate_count ?? 0} already known.${run.error_log ? ` Errors: ${run.error_log}` : ""}`,
      });
      const stats = await fetchSourceStats(sourceId);
      setSourceStats(stats);
      await loadAllData();
    } catch (err: any) {
      setMonitoringNotice({ type: "error", text: "Discovery scan failed: " + err.message });
    } finally {
      setDiscoveryLoading(false);
    }
  };

  const handleRunBackfill = async (sourceId: string) => {
    try {
      setBackfillLoading(true);
      setBackfillResultNotice(null);
      const res = await triggerBackfillBatch(sourceId, {
        batch_size: 10,
        department: backfillDept || undefined,
      });
      setBackfillResultNotice(
        `${res.message || `Backfill ${res.status}`} (attempted ${res.attempted ?? 0}, added ${res.successful ?? 0}, duplicates ${res.duplicates ?? 0}, failed ${res.failed ?? 0}).`
      );
      const stats = await fetchSourceStats(sourceId);
      setSourceStats(stats);
      await loadAllData();
    } catch (err: any) {
      setBackfillResultNotice("Backfill batch failed: " + err.message);
    } finally {
      setBackfillLoading(false);
    }
  };

  const handleApproveDiscovery = async (discoveryId: string) => {
    setApprovingId(discoveryId);
    try {
      const res = await approveDiscovery(discoveryId);
      setMonitoringNotice({ type: "success", text: res?.message || "Approved and added to the library." });
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 409) {
        setMonitoringNotice({ type: "warning", text: `Already handled: ${err.message}` });
      } else {
        setMonitoringNotice({ type: "error", text: "Approval failed: " + err.message });
      }
    }
    try {
      const [refreshedDisc, refreshedDocs] = await Promise.all([fetchDiscoveries(), fetchDocuments()]);
      setDiscoveries(refreshedDisc);
      setDocuments(refreshedDocs);
    } catch (err: any) {
      setLoadError(err.message || "Failed to refresh the review queue.");
    } finally {
      setApprovingId(null);
    }
  };

  const handleRejectDiscovery = async (discoveryId: string) => {
    const reason = prompt("Why are you rejecting this file?");
    if (!reason) return;
    try {
      await rejectDiscovery(discoveryId, reason);
      const refreshedDisc = await fetchDiscoveries();
      setDiscoveries(refreshedDisc);
    } catch (err: any) {
      setMonitoringNotice({ type: "error", text: "Rejection failed: " + err.message });
    }
  };

  const selectedInst = institutions.find((i) => i.id === institutionId);

  if (checkingAuth) {
    return (
      <div className="mx-auto max-w-md space-y-3 py-16" aria-busy="true">
        <SkeletonLine className="h-5 w-48" />
        <SkeletonLine className="h-4 w-full" />
        <SkeletonLine className="h-4 w-3/4" />
      </div>
    );
  }

  if (!currentUser?.is_superuser) {
    return (
      <div className="mx-auto my-10 max-w-md">
        <div className="panel px-6 py-7 shadow-panel">
          <Lock className="h-6 w-6 text-ink-3" strokeWidth={1.75} />
          <h1 className="mt-3 text-[20px] font-semibold text-ink">Administrators only</h1>
          <p className="mt-1.5 text-[14.5px] leading-relaxed text-ink-2">
            The admin console is for the people who approve new circulars and manage the library.
          </p>
          <p className="mt-4 rounded-control bg-sunken px-3 py-2.5 text-[13.5px] text-ink-2">
            {currentUser ? (
              <>
                Signed in as <span className="font-semibold text-ink">{currentUser.full_name}</span> ({currentUser.email}), a standard user.
              </>
            ) : (
              "You are not signed in."
            )}
          </p>
          {loadError && (
            <Notice kind="error" className="mt-3">
              {loadError}
            </Notice>
          )}
          <div className="mt-5 flex flex-wrap gap-2">
            <button type="button" onClick={() => setIsAccountModalOpen(true)} className="btn-primary">
              {currentUser ? "Switch account" : "Sign in"}
            </button>
            <Link href="/" className="btn-secondary">
              Back to circulars
            </Link>
          </div>
        </div>
        <AccountModal
          isOpen={isAccountModalOpen}
          onClose={() => setIsAccountModalOpen(false)}
          currentUser={currentUser}
          onUserChange={(u) => {
            setCurrentUser(u);
            if (u?.is_superuser) loadAllData();
          }}
        />
      </div>
    );
  }

  const openQueue = discoveries.filter((d) => d.status === "VALIDATED");
  const queueItems = queueFilter === "open" ? openQueue : discoveries;

  const tabs: { id: TabId; label: string; count?: number }[] = [
    { id: "queue", label: "Review queue", count: openQueue.length },
    { id: "collection", label: "Website checks" },
    { id: "upload", label: "Upload" },
    { id: "library", label: "Library", count: documents.length },
    { id: "engine", label: "AI engine" },
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-[26px] font-semibold tracking-[-0.015em] text-ink">Admin console</h1>
          <p className="mt-0.5 text-[14.5px] text-ink-3">Approve new circulars, run website checks, and manage the shared library.</p>
        </div>
        <button type="button" onClick={() => setIsGeminiModalOpen(true)} className="btn-secondary self-start sm:self-auto">
          <Sparkles className="h-4 w-4" strokeWidth={1.75} />
          AI setup guide
        </button>
      </div>

      {/* Tabs */}
      <div role="tablist" aria-label="Admin sections" className="-mx-1 flex gap-1 overflow-x-auto overflow-y-hidden border-b border-line px-1">
        {tabs.map((t) => {
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              role="tab"
              type="button"
              aria-selected={active}
              onClick={() => setTab(t.id)}
              className={`relative shrink-0 px-3 pb-2.5 pt-1.5 text-[14px] font-semibold transition-colors ${active ? "text-ink" : "text-ink-3 hover:text-ink"}`}
            >
              {t.label}
              {typeof t.count === "number" && (
                <span
                  className={`ml-1.5 rounded-full px-1.5 py-px text-xs tabular-nums ${
                    active ? "bg-accent text-accent-ink" : "bg-sunken text-ink-2"
                  }`}
                >
                  {t.count}
                </span>
              )}
              {active && (
                <motion.span
                  layoutId="admin-tab"
                  className="absolute inset-x-2 -bottom-px h-[2px] rounded-full bg-accent"
                  transition={{ type: "spring", stiffness: 500, damping: 40 }}
                />
              )}
            </button>
          );
        })}
      </div>

      {/* Messages from the last action stay visible across tabs. */}
      <div className="space-y-2">
        {loadError && <Notice kind="error" onDismiss={() => setLoadError(null)}>{loadError}</Notice>}
        {monitoringNotice && (
          <Notice kind={monitoringNotice.type} onDismiss={() => setMonitoringNotice(null)}>
            <span className="flex flex-wrap items-center gap-2">
              {monitoringNotice.status && <StatusBadge status={monitoringNotice.status} size="sm" />}
              <span>{monitoringNotice.text}</span>
            </span>
          </Notice>
        )}
      </div>

      <motion.div key={tab} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: EASE_OUT }}>
        {tab === "queue" && (
          <section className="panel">
            <PanelHeading
              title="Review queue"
              actions={
                <div className="flex rounded-control bg-sunken p-0.5 text-[13px] font-semibold">
                  {(
                    [
                      ["open", `Needs a decision (${openQueue.length})`],
                      ["all", `Everything found (${discoveries.length})`],
                    ] as const
                  ).map(([id, label]) => (
                    <button
                      key={id}
                      type="button"
                      onClick={() => setQueueFilter(id)}
                      aria-pressed={queueFilter === id}
                      className={`rounded-[5px] px-2.5 py-1 transition-colors ${queueFilter === id ? "bg-surface text-ink shadow-panel" : "text-ink-3 hover:text-ink"}`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              }
            >
              Files the website checker found. Approve to add one to the shared library, or reject it so it is skipped from now on.
            </PanelHeading>

            {loading && discoveries.length === 0 ? (
              <div className="space-y-3 p-5">
                <SkeletonLine className="h-4 w-1/3" />
                <SkeletonLine className="h-4 w-2/3" />
                <SkeletonLine className="h-4 w-1/2" />
              </div>
            ) : queueItems.length === 0 ? (
              <div className="p-5">
                <EmptyState title={queueFilter === "open" ? "Nothing waiting for a decision" : "Nothing found yet"}>
                  {queueFilter === "open"
                    ? "New circulars found on the Bangladesh Bank website will appear here."
                    : "Run a website check to look for new circulars."}
                </EmptyState>
              </div>
            ) : (
              <ul className="divide-y divide-line">
                {queueItems.map((disc, i) => (
                  <motion.li
                    key={disc.id}
                    layout
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.2, delay: Math.min(i, 12) * 0.02 }}
                    className="flex flex-col gap-3 px-5 py-4 md:flex-row md:items-center md:justify-between"
                  >
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="refno">{disc.reference_number || "No reference number"}</span>
                        {disc.department_code && <span className="text-[12.5px] font-semibold text-ink-3">{disc.department_code}</span>}
                        <StatusBadge status={disc.status} size="sm" />
                        {disc.publication_date && <span className="meta">{disc.publication_date}</span>}
                      </div>
                      <p className="text-[15px] font-medium leading-snug text-ink">{disc.title || "Bangladesh Bank publication"}</p>
                      <p className="truncate text-[12.5px] text-ink-3" title={disc.file_url || disc.source_url}>
                        {disc.file_url || disc.source_url}
                      </p>
                      {disc.rejection_reason && <p className="text-[13px] text-bad">Reason: {disc.rejection_reason}</p>}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {disc.file_url && (
                        <a href={disc.file_url} target="_blank" rel="noreferrer" className="btn-ghost">
                          Open file
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      )}
                      {disc.status === "VALIDATED" && (
                        <>
                          <button type="button" onClick={() => handleRejectDiscovery(disc.id)} className="btn-secondary">
                            <X className="h-4 w-4" />
                            Reject
                          </button>
                          <button type="button" onClick={() => handleApproveDiscovery(disc.id)} disabled={approvingId === disc.id} className="btn-primary">
                            <Check className="h-4 w-4" />
                            {approvingId === disc.id ? "Adding..." : "Approve"}
                          </button>
                        </>
                      )}
                    </div>
                  </motion.li>
                ))}
              </ul>
            )}
          </section>
        )}

        {tab === "collection" && (
          <div className="space-y-5">
            <section className="panel">
              <PanelHeading
                title="Bangladesh Bank archive"
                actions={
                  sources.length > 0 && (
                    <button type="button" onClick={() => handleRunDiscoveryScan(sources[0].id)} disabled={discoveryLoading} className="btn-secondary">
                      <RefreshCw className={`h-4 w-4 ${discoveryLoading ? "animate-spin" : ""}`} />
                      {discoveryLoading ? "Scanning..." : "Scan the archive"}
                    </button>
                  )
                }
              >
                What the checker has listed from the website and how much of it is in the library.
              </PanelHeading>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-5 px-5 py-5 md:grid-cols-4">
                <Stat label="Listed on the website" value={sourceStats?.total_discovered ?? "-"} />
                <Stat label="In the library" value={sourceStats?.total_ingested ?? "-"} tone="ok" note="PDFs checked and stored" />
                <Stat label="Waiting to download" value={sourceStats?.total_pending ?? "-"} tone="warn" />
                <div className="min-w-0">
                  <dt className="text-[13px] text-ink-3">Website access</dt>
                  <dd className="mt-1.5">{sourceStats ? <StatusBadge status={sourceStats.access_restriction_status} /> : <span className="text-[22px] font-semibold text-ink">-</span>}</dd>
                </div>
              </dl>

              <div className="border-t border-line px-5 py-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <h3 className="text-[15px] font-semibold text-ink">Download a batch</h3>
                    <p className="text-[13.5px] text-ink-3">
                      Downloads up to 10 listed PDFs, checks each is a real PDF, reads its pages and stores the original.
                    </p>
                  </div>
                  {sources.length > 0 && (
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                      <label htmlFor="backfill-dept" className="sr-only">
                        Department
                      </label>
                      <select id="backfill-dept" value={backfillDept} onChange={(e) => setBackfillDept(e.target.value)} className="field w-auto py-1.5">
                        <option value="">All departments</option>
                        <option value="BRPD">BRPD (Banking Regulation)</option>
                        <option value="DOS">DOS (Off-site Supervision)</option>
                        <option value="FEPD">FEPD (Foreign Exchange)</option>
                        <option value="PSD">PSD (Payment Systems)</option>
                        <option value="SMESPD">SMESPD (SME and Special)</option>
                        <option value="DFIM">DFIM (Financial Institutions)</option>
                        <option value="SFD">SFD (Sustainable Finance)</option>
                      </select>
                      <button type="button" onClick={() => handleRunBackfill(sources[0].id)} disabled={backfillLoading} className="btn-primary">
                        <UploadCloud className="h-4 w-4" />
                        {backfillLoading ? "Downloading..." : "Download 10"}
                      </button>
                    </div>
                  )}
                </div>
                {backfillResultNotice && (
                  <Notice kind={backfillResultNotice.startsWith("Backfill batch failed") ? "error" : "success"} className="mt-3">
                    {backfillResultNotice}
                  </Notice>
                )}
              </div>
            </section>

            <section className="panel">
              <PanelHeading title="Sources">Websites the checker watches for new circulars.</PanelHeading>
              {!loading && sources.length === 0 ? (
                <div className="p-5">
                  <EmptyState title="No sources registered yet" />
                </div>
              ) : (
                <ul className="divide-y divide-line">
                  {sources.map((s) => (
                    <li key={s.id} className="flex flex-col gap-3 px-5 py-4 md:flex-row md:items-start md:justify-between">
                      <div className="min-w-0 space-y-1.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[15px] font-semibold text-ink">{s.name}</span>
                          {s.is_active ? (
                            <Tag tone="ok">Watching</Tag>
                          ) : (
                            <Tag tone="muted">
                              <Pause className="h-3 w-3" /> Paused
                            </Tag>
                          )}
                          <StatusBadge status={s.access_restriction_status} size="sm" />
                        </div>
                        <p className="break-all text-[13px] text-ink-3">{s.base_url}</p>
                        <dl className="flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-ink-3">
                          <div>
                            <dt className="inline">Every </dt>
                            <dd className="inline font-semibold text-ink-2 tabular-nums">{s.polling_frequency_minutes} min</dd>
                          </div>
                          <div>
                            <dt className="inline">Last tried </dt>
                            <dd className="inline font-semibold text-ink-2 tabular-nums">{when(s.last_attempted_run_at)}</dd>
                          </div>
                          <div>
                            <dt className="inline">Last worked </dt>
                            <dd className="inline font-semibold text-ink-2 tabular-nums">{when(s.last_successful_run_at)}</dd>
                          </div>
                        </dl>
                        {s.last_error && (
                          <Notice kind="warning" className="mt-2">
                            {s.last_error}
                          </Notice>
                        )}
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <button type="button" onClick={() => handleToggleActive(s)} className="btn-secondary">
                          {s.is_active ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                          {s.is_active ? "Pause" : "Resume"}
                        </button>
                        <button type="button" onClick={() => handleTriggerRun(s.id)} disabled={triggeringSourceId === s.id} className="btn-primary">
                          <RefreshCw className={`h-4 w-4 ${triggeringSourceId === s.id ? "animate-spin" : ""}`} />
                          {triggeringSourceId === s.id ? "Checking..." : "Check now"}
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        )}

        {tab === "upload" && (
          <section className="panel max-w-3xl">
            <PanelHeading title="Upload a circular">
              Add an official PDF yourself. The file is fingerprinted with SHA-256, the original is stored unchanged, and its text is read page by page.
            </PanelHeading>
            <form onSubmit={handleUpload} className="space-y-4 px-5 py-5">
              <div>
                <label htmlFor="up-file" className="field-label">
                  PDF file
                </label>
                <input
                  key={fileKey}
                  id="up-file"
                  type="file"
                  accept=".pdf"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  className="w-full cursor-pointer rounded-control border border-dashed border-line-strong bg-sunken/50 p-3 text-[13.5px] text-ink-2 file:mr-3 file:cursor-pointer file:rounded-control file:border file:border-line-strong file:bg-surface file:px-3 file:py-1.5 file:text-[13px] file:font-semibold file:text-ink"
                />
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="up-inst" className="field-label">
                    Regulator
                  </label>
                  <select
                    id="up-inst"
                    value={institutionId}
                    onChange={(e) => {
                      setInstitutionId(e.target.value);
                      const inst = institutions.find((i) => i.id === e.target.value);
                      setDepartmentId(inst && inst.departments.length > 0 ? inst.departments[0].id : "");
                    }}
                    className="field"
                  >
                    {institutions.map((inst) => (
                      <option key={inst.id} value={inst.id}>
                        {inst.name} ({inst.code})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="up-dept" className="field-label">
                    Department
                  </label>
                  <select id="up-dept" value={departmentId} onChange={(e) => setDepartmentId(e.target.value)} className="field">
                    <option value="">Not specified</option>
                    {selectedInst?.departments?.map((dept) => (
                      <option key={dept.id} value={dept.id}>
                        {dept.code} - {dept.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="up-ref" className="field-label">
                    Reference number
                  </label>
                  <input
                    id="up-ref"
                    type="text"
                    placeholder="SMESPD Circular No. 05/2026"
                    value={refNumber}
                    onChange={(e) => setRefNumber(e.target.value)}
                    className="field font-mono text-[13px]"
                  />
                </div>
                <div>
                  <label htmlFor="up-type" className="field-label">
                    Document type
                  </label>
                  <select id="up-type" value={docType} onChange={(e) => setDocType(e.target.value)} className="field">
                    <option value="CIRCULAR">Circular</option>
                    <option value="CIRCULAR_LETTER">Circular letter</option>
                    <option value="GUIDELINE">Guideline</option>
                    <option value="NOTIFICATION">Notification</option>
                    <option value="POLICY">Policy</option>
                  </select>
                </div>
              </div>

              <div>
                <label htmlFor="up-title" className="field-label">
                  Title
                </label>
                <input id="up-title" type="text" placeholder="Subject line of the circular" value={title} onChange={(e) => setTitle(e.target.value)} className="field" />
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="up-pub" className="field-label">
                    Date issued
                  </label>
                  <input id="up-pub" type="date" value={pubDate} onChange={(e) => setPubDate(e.target.value)} className="field tabular-nums" />
                </div>
                <div>
                  <label htmlFor="up-eff" className="field-label">
                    Takes effect <span className="font-normal text-ink-3">(optional)</span>
                  </label>
                  <input id="up-eff" type="date" value={effectiveDate} onChange={(e) => setEffectiveDate(e.target.value)} className="field tabular-nums" />
                </div>
              </div>

              <div>
                <label htmlFor="up-url" className="field-label">
                  Original web address <span className="font-normal text-ink-3">(optional)</span>
                </label>
                <input
                  id="up-url"
                  type="url"
                  placeholder="https://www.bb.org.bd/mediaroom/circulars/..."
                  value={sourceUrl}
                  onChange={(e) => setSourceUrl(e.target.value)}
                  className="field font-mono text-[13px]"
                />
              </div>

              <fieldset>
                <legend className="field-label">Who can see it</legend>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {(
                    [
                      ["shared", "Shared library", "Everyone who signs in"],
                      ["private", "Private", "Only you"],
                    ] as const
                  ).map(([value, label, help]) => (
                    <label
                      key={value}
                      className={`flex cursor-pointer items-start gap-2.5 rounded-control border px-3 py-2.5 transition-colors ${
                        visibility === value ? "border-accent bg-accent-soft" : "border-line-strong hover:bg-sunken"
                      }`}
                    >
                      <input
                        type="radio"
                        name="visibility"
                        value={value}
                        checked={visibility === value}
                        onChange={() => setVisibility(value)}
                        className="mt-1 accent-[rgb(var(--accent))]"
                      />
                      <span>
                        <span className="block text-[14px] font-semibold text-ink">{label}</span>
                        <span className="block text-[13px] text-ink-3">{help}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>

              {uploadMessage && <Notice kind={uploadMessage.type === "success" ? "success" : "error"}>{uploadMessage.text}</Notice>}

              <button type="submit" disabled={uploading} className="btn-primary w-full py-2.5 text-[14px] sm:w-auto sm:px-5">
                <UploadCloud className="h-4 w-4" />
                {uploading ? "Uploading and reading pages..." : "Upload circular"}
              </button>
            </form>
          </section>
        )}

        {tab === "library" && (
          <section className="panel">
            <PanelHeading title="Library">Every circular in the system, shared and private, newest first.</PanelHeading>
            {documents.length === 0 ? (
              <div className="p-5">
                {loading ? (
                  <div className="space-y-3">
                    <SkeletonLine className="h-4 w-1/2" />
                    <SkeletonLine className="h-4 w-2/3" />
                  </div>
                ) : (
                  <EmptyState title="The library is empty">Upload a circular or approve one from the review queue to add it.</EmptyState>
                )}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] text-left text-[14px]">
                  <thead>
                    <tr className="border-b border-line text-[12.5px] text-ink-3">
                      <th className="px-5 py-2.5 font-semibold">Circular</th>
                      <th className="px-3 py-2.5 font-semibold">Issued</th>
                      <th className="px-3 py-2.5 font-semibold">Status</th>
                      <th className="px-3 py-2.5 text-right font-semibold">Pages</th>
                      <th className="px-5 py-2.5 text-right font-semibold">
                        <span className="sr-only">PDF</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {documents.map((d) => (
                      <tr key={d.id} className="align-top transition-colors hover:bg-sunken/60">
                        <td className="max-w-[460px] px-5 py-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="refno">{d.reference_number || "Circular"}</span>
                            {d.is_private && <PrivateTag />}
                          </div>
                          <p className="mt-0.5 line-clamp-2 text-ink">{titleWithoutRef(d.title, d.reference_number)}</p>
                        </td>
                        <td className="whitespace-nowrap px-3 py-3 text-ink-2 tabular-nums">{d.publication_date}</td>
                        <td className="px-3 py-3">
                          <StatusBadge status={d.publication_status || "DRAFT"} size="sm" />
                        </td>
                        <td className="px-3 py-3 text-right text-ink-2 tabular-nums">{d.versions?.[0]?.page_count || 0}</td>
                        <td className="px-5 py-3 text-right">
                          <a
                            href={documentPdfUrl(d.id)}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(e) => {
                              if (!d.is_private) return;
                              e.preventDefault();
                              openDocumentPdf(d.id).catch((err) => alert(err.message));
                            }}
                            className="inline-flex items-center gap-1 font-semibold text-accent hover:underline"
                          >
                            <FileText className="h-3.5 w-3.5" />
                            PDF
                            <ArrowUpRight className="h-3 w-3" />
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {tab === "engine" && (
          <section className="panel">
            <PanelHeading
              title="AI engine"
              actions={
                <button type="button" onClick={handleTestProviderConnection} disabled={testingConnection} className="btn-primary">
                  <RefreshCw className={`h-4 w-4 ${testingConnection ? "animate-spin" : ""}`} />
                  {testingConnection ? "Testing..." : "Test connection"}
                </button>
              }
            >
              The model that analyses circulars, and what happened the last time it was called.
            </PanelHeading>
            {connectionTestFeedback && (
              <div className="px-5 pt-4">
                <Notice kind={connectionTestFeedback.success ? "success" : "error"}>{connectionTestFeedback.message}</Notice>
              </div>
            )}
            <dl className="grid grid-cols-1 gap-x-6 gap-y-5 px-5 py-5 sm:grid-cols-2 lg:grid-cols-4">
              <div className="min-w-0">
                <dt className="text-[13px] text-ink-3">Model</dt>
                <dd className="mt-0.5 truncate font-mono text-[15px] font-medium text-ink">{providerInfo?.admin_diagnostics?.model_identifier || activeModel}</dd>
                <dd className="text-[12.5px] text-ink-3">{providerInfo?.configured_provider || "-"}</dd>
              </div>
              <div className="min-w-0">
                <dt className="text-[13px] text-ink-3">Status</dt>
                <dd className="mt-0.5 truncate text-[15px] font-semibold text-ink">{providerInfo?.service_state || "-"}</dd>
                <dd className="text-[12.5px] text-ink-3">
                  {providerInfo?.last_checked_at ? `Checked ${new Date(providerInfo.last_checked_at).toLocaleString()}` : "Not checked yet"}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className="text-[13px] text-ink-3">Last response time</dt>
                <dd className="mt-0.5 text-[15px] font-semibold text-ink tabular-nums">
                  {providerInfo?.admin_diagnostics?.last_latency_ms ? `${providerInfo.admin_diagnostics.last_latency_ms} ms` : "Not tested yet"}
                </dd>
                <dd className="text-[12.5px] text-ink-3">
                  {providerInfo?.admin_diagnostics?.last_status_code ? `HTTP ${providerInfo.admin_diagnostics.last_status_code}` : ""}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className="text-[13px] text-ink-3">Last error</dt>
                <dd className="mt-0.5 text-[15px] font-semibold text-ink break-words">
                  {providerInfo?.admin_diagnostics?.last_error || "None"}
                </dd>
              </div>
            </dl>
          </section>
        )}
      </motion.div>

      <GeminiSetupModal isOpen={isGeminiModalOpen} onClose={() => setIsGeminiModalOpen(false)} isConfigured={geminiConfigured} activeModel={activeModel} />
    </div>
  );
}
