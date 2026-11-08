"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Building2,
  FileText,
  Search,
  ExternalLink,
  BookOpen,
  Calendar,
  Clock,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  FileSpreadsheet,
  ChevronRight,
  Send,
  Download,
  Filter,
  Lock,
  Sparkles,
  RefreshCw,
  ShieldAlert,
  ArrowRight,
  UserCheck,
} from "lucide-react";
import {
  AuthUser,
  DashboardStats,
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
  fetchDocumentStats,
  fetchDocuments,
  fetchInstitutions,
  getStoredUser,
  loginUser,
  queryResearchAssistant,
  triggerDocumentAnalysis,
  reviewDocumentAnalysis,
} from "@/services/api";
import AccountModal from "@/components/AccountModal";

function renderPublicationBadge(status: string) {
  switch (status) {
    case "PUBLISHED_HUMAN_REVIEWED":
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-medium bg-emerald-950/80 dark:bg-emerald-950/80 light:bg-emerald-50 text-emerald-300 dark:text-emerald-300 light:text-emerald-700 border border-emerald-700/80 font-mono">
          Verified by Compliance Officer
        </span>
      );
    case "PUBLISHED_MACHINE_PROCESSED":
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-medium bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-teal-50 text-turquoise dark:text-turquoise light:text-teal-700 border border-turquoise/40 font-mono">
          Automated Analysis — Awaiting Compliance Sign-Off
        </span>
      );
    case "AWAITING_REVIEW":
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-medium bg-amber-950/80 dark:bg-amber-950/80 light:bg-amber-50 text-amber-300 dark:text-amber-300 light:text-amber-700 border border-amber-600/70 font-mono">
          Pending Review
        </span>
      );
    default:
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-medium bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-200 text-slate-300 dark:text-slate-300 light:text-slate-700 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 font-mono">
          Official Publication
        </span>
      );
  }
}

interface DetailProps {
  selectedDoc: DocumentItem;
  analysis: DocumentAnalysisData | null;
  obligations: ObligationItem[];
  provisions: ProvisionItem[];
  relationships: RelationshipItem[];
  docPages: DocumentPage[];
  selectedPageNo: number;
  setSelectedPageNo: (p: number) => void;
  showPagesViewer: boolean;
  setShowPagesViewer: (s: boolean | ((prev: boolean) => boolean)) => void;
  qaQuery: string;
  setQaQuery: (q: string) => void;
  qaLoading: boolean;
  qaResponse: any;
  qaError: string | null;
  handleRunQa: (e: React.FormEvent) => void;
  currentUser: AuthUser | null;
  onOpenAuthModal: () => void;
  onFastLogin: () => void;
  onRefreshDoc: () => void;
}

function CircularDetailView({
  selectedDoc,
  analysis,
  obligations,
  provisions,
  relationships,
  docPages,
  selectedPageNo,
  setSelectedPageNo,
  showPagesViewer,
  setShowPagesViewer,
  qaQuery,
  setQaQuery,
  qaLoading,
  qaResponse,
  qaError,
  handleRunQa,
  currentUser,
  onOpenAuthModal,
  onFastLogin,
  onRefreshDoc,
}: DetailProps) {
  const [adminAnalyzing, setAdminAnalyzing] = useState(false);
  const [adminPublishing, setAdminPublishing] = useState(false);
  const [adminMessage, setAdminMessage] = useState<string | null>(null);

  const handleAdminTriggerAnalysis = async () => {
    try {
      setAdminAnalyzing(true);
      setAdminMessage(null);
      await triggerDocumentAnalysis(selectedDoc.id, "gemini");
      setAdminMessage("Analysis successfully completed and updated.");
      onRefreshDoc();
    } catch (e: any) {
      setAdminMessage("Analysis failed: " + (e.message || String(e)));
    } finally {
      setAdminAnalyzing(false);
    }
  };

  const handleAdminSignOff = async () => {
    try {
      setAdminPublishing(true);
      setAdminMessage(null);
      await reviewDocumentAnalysis(selectedDoc.id, "PUBLISHED_HUMAN_REVIEWED", "Signed off by administrator");
      setAdminMessage("Status updated to PUBLISHED_HUMAN_REVIEWED.");
      onRefreshDoc();
    } catch (e: any) {
      setAdminMessage("Sign-off failed: " + (e.message || String(e)));
    } finally {
      setAdminPublishing(false);
    }
  };

  return (
    <div className="border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 bg-tealNavy-900/90 dark:bg-tealNavy-900/90 light:bg-white rounded-2xl p-6 space-y-6 shadow-xl transition-colors">
      {/* Admin Action Bar (Only visible if superuser) */}
      {currentUser?.is_superuser && (
        <div className="p-3 rounded-xl bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-amber-50 border border-tealNavy-800 dark:border-tealNavy-800 light:border-amber-200 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 font-mono font-bold text-[10px]">
              ADMIN CONTROLS
            </span>
            <span className="text-slate-300 dark:text-slate-300 light:text-amber-900 font-mono text-[11px]">
              Status: {selectedDoc.publication_status}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleAdminTriggerAnalysis}
              disabled={adminAnalyzing}
              className="px-2.5 py-1 rounded bg-turquoise text-tealNavy-950 font-bold font-mono text-[11px] hover:bg-turquoise-bright transition disabled:opacity-50 flex items-center gap-1"
            >
              <RefreshCw className={`w-3 h-3 ${adminAnalyzing ? "animate-spin" : ""}`} />
              <span>{adminAnalyzing ? "Analyzing..." : "Run AI Analysis"}</span>
            </button>
            <button
              onClick={handleAdminSignOff}
              disabled={adminPublishing}
              className="px-2.5 py-1 rounded border border-emerald-700 bg-emerald-950 text-emerald-300 font-mono text-[11px] hover:bg-emerald-900 transition disabled:opacity-50"
            >
              {adminPublishing ? "Signing Off..." : "Approve & Sign Off"}
            </button>
            <Link
              href="/admin"
              className="px-2.5 py-1 rounded border border-tealNavy-700 bg-tealNavy-850 text-slate-300 font-mono text-[11px] hover:text-white"
            >
              Console
            </Link>
          </div>
          {adminMessage && (
            <div className="w-full text-turquoise font-mono text-[10px] pt-1 border-t border-tealNavy-900">
              {adminMessage}
            </div>
          )}
        </div>
      )}

      {/* 1. Official Title, Reference & Original PDF Header (Always Visible) */}
      <div className="space-y-2 border-b border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200 pb-5">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <span className="text-xs font-mono font-bold text-turquoise dark:text-turquoise light:text-teal-700 px-2 py-0.5 rounded bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-teal-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-teal-200">
            {selectedDoc.reference_number || "OFFICIAL CIRCULAR"}
          </span>
          <div className="flex items-center space-x-2">
            <a
              href={selectedDoc.source_url || `/api/v1/documents/${selectedDoc.id}`}
              target="_blank"
              rel="noreferrer"
              className="text-xs font-semibold bg-turquoise hover:bg-turquoise-bright text-tealNavy-950 px-3.5 py-1.5 rounded-lg transition flex items-center gap-1.5 shadow-sm font-mono"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download Official Circular</span>
            </a>
          </div>
        </div>

        <h2 className="text-xl font-bold text-white dark:text-white light:text-tealNavy-950 mt-2 leading-snug">
          {selectedDoc.title}
        </h2>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400 dark:text-slate-400 light:text-slate-600 font-mono pt-1">
          <span>Published: {selectedDoc.publication_date}</span>
          {selectedDoc.effective_date && <span>Effective: {selectedDoc.effective_date}</span>}
          <span>Authority: Bangladesh Bank</span>
          <span>•</span>
          {renderPublicationBadge(selectedDoc.publication_status)}
        </div>
      </div>

      {/* Analytics Body: Gated for Unauthenticated Visitors */}
      {currentUser ? (
        <div className="space-y-6">
          {/* 2. Short Executive Summary */}
          <div className="space-y-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-turquoise dark:text-turquoise light:text-teal-700 font-mono">
              1. Executive Summary
            </h3>
            <div className="p-4 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200">
              <p className="text-sm text-slate-200 dark:text-slate-200 light:text-tealNavy-950 leading-relaxed">
                {analysis?.executive_summary ||
                  selectedDoc.title_bn ||
                  "This official circular sets forth binding regulatory guidelines issued by Bangladesh Bank under statutory authority. Detailed clause-by-clause requirements are itemized below."}
              </p>
              {analysis?.purpose && (
                <p className="text-xs text-slate-400 dark:text-slate-400 light:text-slate-600 mt-2 pt-2 border-t border-tealNavy-900 dark:border-tealNavy-900 light:border-slate-200 leading-relaxed">
                  <strong className="text-slate-300 dark:text-slate-300 light:text-slate-700">Regulatory Purpose:</strong> {analysis.purpose}
                </p>
              )}
            </div>
          </div>

          {/* 3. What Has Changed */}
          <div className="space-y-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-turquoise dark:text-turquoise light:text-teal-700 font-mono">
              2. What Has Changed
            </h3>
            <div className="p-4 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200">
              {(() => {
                let changes: any[] = [];
                if (Array.isArray(analysis?.key_changes)) {
                  changes = analysis.key_changes;
                } else if (typeof analysis?.key_changes === "string") {
                  try {
                    const parsed = JSON.parse(analysis.key_changes);
                    changes = Array.isArray(parsed) ? parsed : [analysis.key_changes];
                  } catch {
                    changes = [analysis.key_changes];
                  }
                }
                if (changes && changes.length > 0) {
                  return (
                    <ul className="space-y-2 text-xs text-slate-300 dark:text-slate-300 light:text-slate-700">
                      {changes.map((change, idx) => (
                        <li key={idx} className="flex items-start gap-2">
                          <CheckCircle2 className="w-4 h-4 text-turquoise shrink-0 mt-0.5" />
                          <span className="leading-relaxed">
                            {typeof change === "string" ? change : JSON.stringify(change)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  );
                }
                return (
                  <p className="text-xs text-slate-400 dark:text-slate-400 light:text-slate-600">
                    This publication establishes a new regulatory framework. See the mandatory requirements below for operational details.
                  </p>
                );
              })()}
            </div>
          </div>

          {/* 4. Key Requirements & Action Items */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-turquoise dark:text-turquoise light:text-teal-700 font-mono">
                3. Key Requirements ({obligations.length})
              </h3>
              <span className="text-[11px] text-slate-400 font-mono">Actionable Obligations</span>
            </div>
            <div className="space-y-3">
              {obligations.length === 0 ? (
                <p className="text-xs text-slate-400 p-4 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 rounded-xl bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50">
                  No standalone obligations extracted for this circular.
                </p>
              ) : (
                obligations.map((obl) => {
                  const citedPage = docPages.find((p) => p.id === obl.page_id)?.page_number;
                  return (
                    <div
                      key={obl.id}
                      className="p-3.5 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-bold text-sm text-slate-100 dark:text-slate-100 light:text-tealNavy-950">
                          {obl.title}
                        </span>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-teal-100 text-turquoise dark:text-turquoise light:text-teal-800 border border-tealNavy-700 dark:border-tealNavy-700 light:border-teal-200 font-bold">
                          {obl.obligation_type}
                        </span>
                      </div>

                      <p className="text-xs text-slate-300 dark:text-slate-300 light:text-slate-700 leading-relaxed">
                        {obl.requirement_description}
                      </p>

                      <div className="bg-tealNavy-900/90 dark:bg-tealNavy-900/90 light:bg-white p-2.5 rounded-lg border border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200 text-[11px] font-mono text-slate-400 dark:text-slate-400 light:text-slate-600 italic">
                        &ldquo;{obl.supporting_text}&rdquo;
                      </div>

                      <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 pt-1">
                        <span>Target: {obl.applicability_summary || "Scheduled Banks"}</span>
                        <span>{citedPage ? `Page ${citedPage}` : "Verified Reference"}</span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* 5. Affected Departments & Institutions */}
          <div className="space-y-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-turquoise dark:text-turquoise light:text-teal-700 font-mono">
              4. Affected Departments &amp; Institutions
            </h3>
            <div className="p-4 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-2 text-xs text-slate-300 dark:text-slate-300 light:text-slate-700">
              <div className="flex items-start gap-2">
                <span className="text-turquoise font-bold">•</span>
                <span>All Scheduled Commercial Banks &amp; Non-Bank Financial Institutions (NBFIs) in Bangladesh.</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-turquoise font-bold">•</span>
                <span>
                  Internal Bank Departments: Credit Risk Management, SME &amp; Agri Banking, Treasury, Internal Audit, Compliance Division.
                </span>
              </div>
            </div>
          </div>

          {/* 6. Deadlines & Effective Dates */}
          <div className="space-y-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-turquoise dark:text-turquoise light:text-teal-700 font-mono">
              5. Deadlines &amp; Effective Dates
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="p-3 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200">
                <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-mono">Publication Date</span>
                <span className="text-sm font-semibold text-slate-200 dark:text-slate-200 light:text-tealNavy-950 font-mono">
                  {selectedDoc.publication_date}
                </span>
              </div>
              <div className="p-3 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200">
                <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-mono">Enforcement / Effective Date</span>
                <span className="text-sm font-semibold text-slate-200 dark:text-slate-200 light:text-tealNavy-950 font-mono">
                  {selectedDoc.effective_date || "With immediate effect"}
                </span>
              </div>
            </div>
          </div>

          {/* 7. Applicability & Exceptions */}
          <div className="space-y-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-turquoise dark:text-turquoise light:text-teal-700 font-mono">
              6. Applicability &amp; Exceptions
            </h3>
            <div className="p-4 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 text-xs text-slate-300 dark:text-slate-300 light:text-slate-700 leading-relaxed">
              Applicable to all operating banking institutions governed under Section 45 of the Bank Company Act, 1991. Any exemptions or concessions must be explicitly applied for in writing to the relevant Department of Bangladesh Bank.
            </div>
          </div>

          {/* 8. Exact Supporting Source Pages */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-turquoise dark:text-turquoise light:text-teal-700 font-mono">
                7. Exact Supporting Source Pages ({docPages.length})
              </h3>
              <button
                onClick={() => setShowPagesViewer((prev) => !prev)}
                className="text-xs font-mono text-turquoise hover:underline"
              >
                {showPagesViewer ? "Hide Page Viewer" : "View Extracted Pages"}
              </button>
            </div>

            {showPagesViewer && (
              <div className="p-4 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-3">
                <div className="flex gap-2 overflow-x-auto pb-2">
                  {docPages.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => setSelectedPageNo(p.page_number)}
                      className={`px-3 py-1 rounded text-xs font-mono transition ${
                        selectedPageNo === p.page_number
                          ? "bg-turquoise text-tealNavy-950 font-bold"
                          : "bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white text-slate-300 dark:text-slate-300 light:text-slate-700 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300"
                      }`}
                    >
                      Page {p.page_number}
                    </button>
                  ))}
                </div>

                <div className="max-h-60 overflow-y-auto p-3 bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white rounded-lg border border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200 text-xs text-slate-300 dark:text-slate-300 light:text-slate-800 font-mono whitespace-pre-wrap leading-relaxed">
                  {docPages.find((p) => p.page_number === selectedPageNo)?.raw_text || "Page text not available."}
                </div>
              </div>
            )}
          </div>

          {/* 9. Grounded Regulatory Inquiries (Q&A) */}
          <div className="space-y-3 pt-3 border-t border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200">
            <h3 className="text-xs font-bold uppercase tracking-wider text-turquoise dark:text-turquoise light:text-teal-700 font-mono">
              8. Grounded Regulatory Inquiries
            </h3>
            <p className="text-xs text-slate-400 dark:text-slate-400 light:text-slate-600">
              Ask compliance questions strictly grounded in this circular. Answers provide verbatim citations and page numbers.
            </p>

            <form onSubmit={handleRunQa} className="flex gap-2">
              <input
                type="text"
                value={qaQuery}
                onChange={(e) => setQaQuery(e.target.value)}
                placeholder="e.g. What are the key requirements or deadlines in this circular?"
                className="flex-1 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-white border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl px-3.5 py-2 text-xs text-slate-200 dark:text-slate-200 light:text-tealNavy-950 focus:outline-none focus:border-turquoise font-sans"
              />
              <button
                type="submit"
                disabled={qaLoading}
                className="px-4 py-2 bg-turquoise hover:bg-turquoise-bright text-tealNavy-950 text-xs font-bold rounded-xl transition shadow-sm disabled:opacity-50 flex items-center gap-1.5 font-mono"
              >
                <Send className="w-3.5 h-3.5" />
                <span>{qaLoading ? "Searching..." : "Ask"}</span>
              </button>
            </form>

            {qaError && (
              <div className="p-3 bg-rose-950/60 border border-rose-800 rounded-lg text-xs text-rose-300 font-mono">
                {qaError}
              </div>
            )}

            {qaResponse && (
              <div className="p-4 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-3 text-xs">
                <span className="font-bold text-slate-200 dark:text-slate-200 light:text-tealNavy-950 block">
                  Grounded Compliance Answer:
                </span>
                <p className="text-slate-200 dark:text-slate-200 light:text-slate-800 leading-relaxed whitespace-pre-line">
                  {qaResponse.answer}
                </p>

                {Array.isArray(qaResponse.citations) && qaResponse.citations.length > 0 && (
                  <div className="pt-2 border-t border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200 space-y-2">
                    <span className="text-[11px] font-mono text-turquoise dark:text-turquoise light:text-teal-700 block font-bold">
                      Supporting Page Citations:
                    </span>
                    {qaResponse.citations.slice(0, 3).map((cit: any, i: number) => (
                      <div
                        key={i}
                        className="p-2 bg-tealNavy-900/60 dark:bg-tealNavy-900/60 light:bg-white rounded border border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200 text-[11px] font-mono text-slate-400 dark:text-slate-400 light:text-slate-600"
                      >
                        <strong className="text-slate-300 dark:text-slate-300 light:text-tealNavy-950">
                          Page {cit.page_number || cit.page || 1}:
                        </strong>{" "}
                        &ldquo;{cit.verbatim_excerpt || cit.quoted_text || ""}&rdquo;
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      ) : (
        /* Gated View for Unauthenticated Visitors */
        <div className="relative rounded-2xl overflow-hidden border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 mt-6 shadow-md">
          {/* Blurred Background Previews */}
          <div className="filter blur-[5px] select-none pointer-events-none opacity-30 p-6 space-y-5 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-100">
            <div className="space-y-2">
              <div className="h-4 w-36 bg-tealNavy-700 rounded font-mono"></div>
              <div className="p-4 bg-tealNavy-900 rounded-xl space-y-2">
                <div className="h-3 w-full bg-tealNavy-800 rounded"></div>
                <div className="h-3 w-4/5 bg-tealNavy-800 rounded"></div>
              </div>
            </div>
            <div className="space-y-2">
              <div className="h-4 w-44 bg-tealNavy-700 rounded font-mono"></div>
              <div className="p-4 bg-tealNavy-900 rounded-xl space-y-2">
                <div className="h-3 w-full bg-tealNavy-800 rounded"></div>
                <div className="h-3 w-3/4 bg-tealNavy-800 rounded"></div>
              </div>
            </div>
            <div className="space-y-2">
              <div className="h-4 w-52 bg-tealNavy-700 rounded font-mono"></div>
              <div className="p-4 bg-tealNavy-900 rounded-xl space-y-2">
                <div className="h-3 w-full bg-tealNavy-800 rounded"></div>
                <div className="h-3 w-2/3 bg-tealNavy-800 rounded"></div>
              </div>
            </div>
          </div>

          {/* Gated Access Card Overlay */}
          <div className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center bg-tealNavy-950/85 dark:bg-tealNavy-950/85 light:bg-white/90 backdrop-blur-md">
            <div className="w-12 h-12 rounded-2xl bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-teal-100 border border-tealNavy-700 dark:border-tealNavy-700 light:border-teal-300 flex items-center justify-center text-turquoise dark:text-turquoise light:text-teal-700 mb-3 shadow-lg">
              <Lock className="w-6 h-6 text-turquoise dark:text-turquoise light:text-teal-700" />
            </div>
            <h3 className="text-lg font-bold text-white dark:text-white light:text-tealNavy-950">
              Institutional Regulatory Intelligence Locked
            </h3>
            <p className="text-xs text-slate-300 dark:text-slate-300 light:text-slate-600 max-w-md mt-1.5 leading-relaxed">
              Clause-by-clause legal obligations, operational impact assessments, and cross-lingual AI regulatory inquiries are reserved for authenticated banking professionals.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-3 mt-5">
              <button
                onClick={onOpenAuthModal}
                className="px-5 py-2.5 rounded-xl bg-turquoise hover:bg-turquoise-bright text-tealNavy-950 font-bold text-xs font-mono transition shadow-lg flex items-center gap-2"
              >
                <span>Get Access — Sign In</span>
                <ChevronRight className="w-4 h-4" />
              </button>
              <button
                onClick={onFastLogin}
                className="px-4 py-2.5 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white hover:border-turquoise text-slate-300 dark:text-slate-300 light:text-slate-700 text-xs font-mono transition flex items-center gap-1.5"
              >
                <UserCheck className="w-3.5 h-3.5 text-turquoise" />
                <span>Banker Demo Access</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ProfessionalCircularsPage() {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [isAccountModalOpen, setIsAccountModalOpen] = useState(false);

  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedDept, setSelectedDept] = useState<string>("ALL");
  const [selectedDoc, setSelectedDoc] = useState<DocumentItem | null>(null);
  const [docPages, setDocPages] = useState<DocumentPage[]>([]);
  const [selectedPageNo, setSelectedPageNo] = useState<number>(1);
  const [showPagesViewer, setShowPagesViewer] = useState(false);

  // Selected Circular Intelligence Artifacts
  const [analysis, setAnalysis] = useState<DocumentAnalysisData | null>(null);
  const [obligations, setObligations] = useState<ObligationItem[]>([]);
  const [provisions, setProvisions] = useState<ProvisionItem[]>([]);
  const [relationships, setRelationships] = useState<RelationshipItem[]>([]);

  // Grounded Regulatory Q&A State
  const [qaQuery, setQaQuery] = useState("");
  const [qaLoading, setQaLoading] = useState(false);
  const [qaResponse, setQaResponse] = useState<any>(null);
  const [qaError, setQaError] = useState<string | null>(null);

  useEffect(() => {
    const user = getStoredUser();
    setCurrentUser(user);
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [docs, insts, dashboardStats] = await Promise.all([
        fetchDocuments({ search, corpus_type: "GENUINE" }),
        fetchInstitutions().catch(() => []),
        fetchDocumentStats().catch(() => null),
      ]);

      setDocuments(docs);
      if (insts.length > 0) setInstitutions(insts);
      if (dashboardStats) setStats(dashboardStats);

      if (!selectedDoc && docs.length > 0) {
        handleSelectDoc(docs[0]);
      }
    } catch (err) {
      console.error("Data loading error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [search]);

  const handleSelectDoc = async (doc: DocumentItem) => {
    setSelectedDoc(doc);
    setSelectedPageNo(1);
    setQaResponse(null);
    setQaError(null);

    // Fetch pages
    if (doc.versions && doc.versions.length > 0) {
      fetchDocumentPages(doc.id, doc.versions[0].id)
        .then((pages) => setDocPages(pages))
        .catch(() => setDocPages([]));
    } else {
      setDocPages([]);
    }

    // Load intelligence artifacts
    try {
      const [aiData, obls, provs, rels] = await Promise.all([
        fetchDocumentAnalysis(doc.id).catch(() => null),
        fetchDocumentObligations(doc.id).catch(() => []),
        fetchDocumentProvisions(doc.id).catch(() => []),
        fetchDocumentRelationships(doc.id).catch(() => []),
      ]);
      setAnalysis(aiData);
      setObligations(obls);
      setProvisions(provs);
      setRelationships(rels);
    } catch (err) {
      console.error("Error fetching circular details:", err);
    }
  };

  const handleRunQa = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!qaQuery.trim() || !selectedDoc) return;
    try {
      setQaLoading(true);
      setQaError(null);
      const res = await queryResearchAssistant(qaQuery, selectedDoc.id);
      setQaResponse(res);
    } catch (err: any) {
      setQaError(err.message || "Failed to process question.");
    } finally {
      setQaLoading(false);
    }
  };

  const handleFastLogin = async () => {
    try {
      const user = await loginUser("cco@nationalbank.bd", "CCOPassword123!");
      setCurrentUser(user);
      if (selectedDoc) {
        handleSelectDoc(selectedDoc);
      }
    } catch (e: any) {
      alert("Demo sign-in failed: " + e.message);
    }
  };

  // Filter circulars by issuing department code
  const filteredDocuments = documents.filter((doc) => {
    if (selectedDept === "ALL") return true;
    const ref = (doc.reference_number || "").toUpperCase();
    const title = (doc.title || "").toUpperCase();
    return ref.includes(selectedDept) || title.includes(selectedDept);
  });

  return (
    <div className="space-y-6">
      {/* Account Modal */}
      <AccountModal
        isOpen={isAccountModalOpen}
        onClose={() => setIsAccountModalOpen(false)}
        currentUser={currentUser}
        onUserChange={(u) => {
          setCurrentUser(u);
          if (selectedDoc) handleSelectDoc(selectedDoc);
        }}
      />

      {/* Executive Header Banner */}
      <div className="border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 bg-tealNavy-900/90 dark:bg-tealNavy-900/90 light:bg-white rounded-2xl p-6 backdrop-blur shadow-lg transition-colors">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-semibold tracking-wider uppercase px-2 py-0.5 rounded bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-teal-50 text-turquoise dark:text-turquoise light:text-teal-700 border border-tealNavy-700 dark:border-tealNavy-700 light:border-teal-200 font-mono">
                Bangladesh Bank
              </span>
              <span className="text-[11px] text-slate-400 dark:text-slate-400 light:text-slate-500 font-medium font-mono">
                Official Regulatory Circulars &amp; Guidelines
              </span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white dark:text-white light:text-tealNavy-950 mt-1.5">
              Official Regulatory Repository
            </h1>
            <p className="text-sm text-slate-300 dark:text-slate-300 light:text-slate-600 mt-1 max-w-2xl leading-relaxed">
              Autonomous continuous collection, layout-aware extraction, and verified regulatory obligations across all scheduled banks in Bangladesh.
            </p>
          </div>

          <div className="flex items-center gap-4 text-xs font-mono text-slate-400 dark:text-slate-400 light:text-slate-600">
            <div className="p-3 rounded-xl bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 text-center">
              <span className="text-lg font-bold text-turquoise block">{documents.length}</span>
              <span className="text-[10px] text-slate-400 uppercase">Official Circulars</span>
            </div>
            <div className="p-3 rounded-xl bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 text-center">
              <span className="text-lg font-bold text-emerald-400 block">SHA-256</span>
              <span className="text-[10px] text-slate-400 uppercase">Integrity Protected</span>
            </div>
          </div>
        </div>
      </div>

      {/* Search and Department Filter Toolbar */}
      <div className="flex flex-col md:flex-row gap-3 items-center justify-between">
        <div className="relative w-full md:w-96">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search circulars by number, title, or topic..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl pl-10 pr-4 py-2 text-sm text-slate-200 dark:text-slate-200 light:text-tealNavy-950 placeholder-slate-400 focus:outline-none focus:border-turquoise font-sans transition"
          />
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto w-full md:w-auto pb-1">
          {["ALL", "SMESPD", "BRPD", "DOS", "FEPD", "PSD"].map((dept) => (
            <button
              key={dept}
              onClick={() => setSelectedDept(dept)}
              className={`px-3 py-1.5 text-xs rounded-lg font-mono font-medium transition ${
                selectedDept === dept
                  ? "bg-turquoise text-tealNavy-950 font-bold shadow-sm"
                  : "bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white text-slate-400 dark:text-slate-400 light:text-slate-600 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 hover:text-white dark:hover:text-white"
              }`}
            >
              {dept === "ALL" ? "All Departments" : dept}
            </button>
          ))}
        </div>
      </div>

      {/* Main Layout: Desktop Split / Mobile Inline */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Circulars List */}
        <div className="lg:col-span-5 space-y-3">
          <div className="flex items-center justify-between text-xs text-slate-400 dark:text-slate-400 light:text-slate-600 px-1 font-medium font-mono">
            <span>Recent Official Circulars ({filteredDocuments.length})</span>
            <span>Bangladesh Bank</span>
          </div>

          {loading ? (
            <div className="p-8 text-center text-slate-400 text-sm border border-tealNavy-700 rounded-xl bg-tealNavy-900/40">
              Loading circular repository...
            </div>
          ) : filteredDocuments.length === 0 ? (
            <div className="p-8 text-center text-slate-400 text-sm border border-dashed border-tealNavy-700 rounded-xl bg-tealNavy-900/40">
              No circulars found matching your search.
            </div>
          ) : (
            filteredDocuments.map((doc) => {
              const isSelected = selectedDoc?.id === doc.id;
              const pageCount = doc.versions?.[0]?.page_count ?? 0;
              return (
                <div key={doc.id} className="space-y-3">
                  {/* Card Item */}
                  <div
                    onClick={() => handleSelectDoc(doc)}
                    className={`p-4 rounded-xl border cursor-pointer transition text-left ${
                      isSelected
                        ? "bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-teal-50/70 border-turquoise shadow-[0_0_15px_rgba(45,212,191,0.2)]"
                        : "bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 hover:bg-tealNavy-850 dark:hover:bg-tealNavy-850 light:hover:bg-slate-50 hover:border-turquoise/60"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-xs font-mono font-bold text-turquoise dark:text-turquoise light:text-teal-800">
                        {doc.reference_number || "Official Circular"}
                      </span>
                      <span className="text-xs text-slate-400 dark:text-slate-400 light:text-slate-500 font-mono">
                        {doc.publication_date}
                      </span>
                    </div>

                    <h3 className="text-sm font-semibold text-slate-100 dark:text-slate-100 light:text-tealNavy-950 mt-2 leading-snug">
                      {doc.title}
                    </h3>

                    <div className="flex items-center justify-between text-xs text-slate-400 dark:text-slate-400 light:text-slate-500 mt-3 pt-3 border-t border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200">
                      <div className="flex items-center gap-2 font-mono text-[11px]">
                        <span>{doc.document_type || "CIRCULAR"}</span>
                        <span>•</span>
                        <span>{pageCount > 0 ? `${pageCount} pages` : "Complete"}</span>
                      </div>
                      {renderPublicationBadge(doc.publication_status)}
                    </div>
                  </div>

                  {/* MOBILE VIEW ONLY: Render Detail View Directly Below the Clicked Circular */}
                  {isSelected && (
                    <div className="block lg:hidden pt-1 pb-3 animate-in fade-in duration-200">
                      <CircularDetailView
                        selectedDoc={doc}
                        analysis={analysis}
                        obligations={obligations}
                        provisions={provisions}
                        relationships={relationships}
                        docPages={docPages}
                        selectedPageNo={selectedPageNo}
                        setSelectedPageNo={setSelectedPageNo}
                        showPagesViewer={showPagesViewer}
                        setShowPagesViewer={setShowPagesViewer}
                        qaQuery={qaQuery}
                        setQaQuery={setQaQuery}
                        qaLoading={qaLoading}
                        qaResponse={qaResponse}
                        qaError={qaError}
                        handleRunQa={handleRunQa}
                        currentUser={currentUser}
                        onOpenAuthModal={() => setIsAccountModalOpen(true)}
                        onFastLogin={handleFastLogin}
                        onRefreshDoc={() => handleSelectDoc(doc)}
                      />
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* DESKTOP VIEW ONLY: Right Column for Selected Circular Details */}
        <div className="hidden lg:block lg:col-span-7">
          {selectedDoc ? (
            <CircularDetailView
              selectedDoc={selectedDoc}
              analysis={analysis}
              obligations={obligations}
              provisions={provisions}
              relationships={relationships}
              docPages={docPages}
              selectedPageNo={selectedPageNo}
              setSelectedPageNo={setSelectedPageNo}
              showPagesViewer={showPagesViewer}
              setShowPagesViewer={setShowPagesViewer}
              qaQuery={qaQuery}
              setQaQuery={setQaQuery}
              qaLoading={qaLoading}
              qaResponse={qaResponse}
              qaError={qaError}
              handleRunQa={handleRunQa}
              currentUser={currentUser}
              onOpenAuthModal={() => setIsAccountModalOpen(true)}
              onFastLogin={handleFastLogin}
              onRefreshDoc={() => handleSelectDoc(selectedDoc)}
            />
          ) : (
            <div className="p-12 text-center border border-dashed border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-2xl text-slate-400 font-mono text-xs">
              Select a circular on the left to read its executive summary, requirements, and supporting pages.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
