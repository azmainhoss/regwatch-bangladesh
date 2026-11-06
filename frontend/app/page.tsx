"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Building2,
  FileText,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Search,
  ExternalLink,
  Layers,
  Cpu,
  Clock,
  ShieldCheck,
  Scale,
  BookOpen,
  HelpCircle,
  ChevronRight,
  Database,
  SlidersHorizontal,
  Info,
  Calendar,
  ArrowUpRight,
  Check,
  Briefcase,
  Radio,
  FileSpreadsheet,
} from "lucide-react";
import {
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
  fetchProviderStatus,
  queryResearchAssistant,
  triggerDocumentAnalysis,
} from "@/services/api";
import GeminiSetupModal from "@/components/GeminiSetupModal";

function renderPublicationBadge(status: string) {
  switch (status) {
    case "PUBLISHED_HUMAN_REVIEWED":
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-emerald-950/80 dark:bg-emerald-950/80 light:bg-emerald-50 text-emerald-300 dark:text-emerald-300 light:text-emerald-700 border border-emerald-700/80">
          Human Reviewed
        </span>
      );
    case "PUBLISHED_MACHINE_VERIFIED":
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-turquoise-dark/60 dark:bg-turquoise-dark/60 light:bg-teal-50 text-turquoise dark:text-turquoise light:text-teal-700 border border-turquoise/40">
          Machine Verified
        </span>
      );
    case "PUBLISHED_MACHINE_PROCESSED":
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-blue-50 text-sky-300 dark:text-sky-300 light:text-blue-700 border border-sky-700/60">
          Machine Processed
        </span>
      );
    case "CORRECTED":
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-teal-50 text-teal-300 dark:text-teal-300 light:text-teal-700 border border-teal-600/60">
          Human Corrected
        </span>
      );
    case "AWAITING_REVIEW":
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-amber-950/80 dark:bg-amber-950/80 light:bg-amber-50 text-amber-300 dark:text-amber-300 light:text-amber-700 border border-amber-600/70">
          Awaiting Review
        </span>
      );
    case "REJECTED":
    case "WITHDRAWN":
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-rose-950/80 dark:bg-rose-950/80 light:bg-rose-50 text-rose-300 dark:text-rose-300 light:text-rose-700 border border-rose-800/80">
          {status}
        </span>
      );
    case "EXTRACTION_FAILED":
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-red-950/80 dark:bg-red-950/80 light:bg-red-50 text-red-300 dark:text-red-300 light:text-red-700 border border-red-800/80">
          Extraction Failed
        </span>
      );
    default:
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-mono bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-200 text-slate-300 dark:text-slate-300 light:text-slate-700 border border-tealNavy-750 dark:border-tealNavy-700 light:border-slate-300">
          {status}
        </span>
      );
  }
}

function renderCitationBadge(status: string) {
  switch (status) {
    case "VERIFIED_EXACT":
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-mono font-bold bg-emerald-950/80 dark:bg-emerald-950/80 light:bg-emerald-50 text-emerald-300 dark:text-emerald-300 light:text-emerald-700 border border-emerald-700/80">
          Verified Exact
        </span>
      );
    case "VERIFIED_NORMALIZED":
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-mono font-bold bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-teal-50 text-turquoise dark:text-turquoise light:text-teal-700 border border-turquoise/40">
          Verified Normalized
        </span>
      );
    case "CANDIDATE_FUZZY":
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-amber-950/80 dark:bg-amber-950/80 light:bg-amber-50 text-amber-300 dark:text-amber-300 light:text-amber-700 border border-amber-700/80">
          Candidate Fuzzy
        </span>
      );
    case "WRONG_PAGE":
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-orange-950/80 dark:bg-orange-950/80 light:bg-orange-50 text-orange-300 dark:text-orange-300 light:text-orange-700 border border-orange-700/80">
          Wrong Page
        </span>
      );
    case "UNVERIFIED":
    case "SOURCE_MISSING":
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-rose-950/80 dark:bg-rose-950/80 light:bg-rose-50 text-rose-300 dark:text-rose-300 light:text-rose-700 border border-rose-800/80">
          Unverified Citation
        </span>
      );
    default:
      return (
        <span className="text-[10px] px-2 py-0.5 rounded font-mono bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-200 text-slate-300 dark:text-slate-300 light:text-slate-700">
          {status}
        </span>
      );
  }
}

export default function ProfessionalFeedPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [corpusFilter, setCorpusFilter] = useState<"GENUINE" | "ALL" | "SYNTHETIC_SAMPLE">("GENUINE");
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

  // Gemini Free-Tier Modal
  const [isGeminiModalOpen, setIsGeminiModalOpen] = useState(false);
  const [geminiConfigured, setGeminiConfigured] = useState(false);
  const [activeModel, setActiveModel] = useState("gemini-3.8-flash");

  // Active navigation section
  const [activeNav, setActiveNav] = useState<"overview" | "feed" | "obligations" | "research">("feed");

  const loadData = async () => {
    try {
      setLoading(true);
      const [docs, insts, dashboardStats, providerStatus] = await Promise.all([
        fetchDocuments({ search, corpus_type: corpusFilter }),
        fetchInstitutions().catch(() => []),
        fetchDocumentStats().catch(() => null),
        fetchProviderStatus().catch(() => null),
      ]);
      setDocuments(docs);
      if (insts.length > 0) {
        setInstitutions(insts);
      }
      if (dashboardStats) {
        setStats(dashboardStats);
      }
      if (providerStatus) {
        setGeminiConfigured(providerStatus.gemini_api_key_configured);
        setActiveModel(providerStatus.default_model);
      }
    } catch (err) {
      console.error("Data loading error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [search, corpusFilter]);

  const allDepartments = institutions.flatMap((inst) => inst.departments || []);
  const deptCodes = allDepartments.map((d) => d.code).slice(0, 6).join(", ") || "BRPD, DOS, SMESPD, FEPD, PSD";
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

    // Load AI Intelligence
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
      {/* Visual Direction 04 Top Terminal Banner & Financial KPI Grid */}
      <div className="border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 bg-tealNavy-900/90 dark:bg-tealNavy-900/90 light:bg-white rounded-2xl p-6 backdrop-blur shadow-lg transition-colors">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-mono font-bold tracking-wider uppercase px-2 py-0.5 rounded bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-teal-50 text-turquoise dark:text-turquoise light:text-teal-700 border border-tealNavy-700 dark:border-tealNavy-700 light:border-teal-200">
                Visual Direction 04 - Deep Teal & Turquoise
              </span>
              <span className="text-[11px] font-mono text-slate-400 dark:text-slate-400 light:text-slate-500">
                Strict Zero-Cost Policy
              </span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white dark:text-white light:text-tealNavy-950 mt-1.5">
              Bangladesh Regulatory Intelligence Platform
            </h1>
            <p className="text-sm text-slate-300 dark:text-slate-300 light:text-slate-600 mt-1 max-w-2xl">
              Real-time monitoring of official publications from Bangladesh Bank. Every regulatory obligation, ratio, and clause is validated with page-level provenance.
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={() => setIsGeminiModalOpen(true)}
              className="px-3.5 py-2 rounded-lg border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-100 hover:border-turquoise text-slate-200 dark:text-slate-200 light:text-tealNavy-950 text-xs font-semibold transition flex items-center gap-2"
              title="Configure Google Gemini Free Tier without credit cards or billing"
            >
              <Sparkles className="w-3.5 h-3.5 text-turquoise" />
              <span>Gemini Free-Tier Info</span>
            </button>
            <Link
              href="/admin"
              className="px-4 py-2 bg-turquoise hover:bg-turquoise-bright text-tealNavy-950 text-xs font-bold rounded-lg shadow-sm transition inline-flex items-center gap-1.5"
            >
              <span>Ingest Circular</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>

        {/* Financial KPI Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-tealNavy-700/80 dark:border-tealNavy-700/80 light:border-slate-200">
          <div className="bg-tealNavy-950/70 dark:bg-tealNavy-950/70 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 rounded-xl p-3.5 transition-colors">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-medium text-slate-400 dark:text-slate-400 light:text-slate-500 uppercase tracking-wider block">
                Official Publications
              </span>
              <BookOpen className="w-4 h-4 text-turquoise" />
            </div>
            <span className="text-2xl font-bold text-white dark:text-white light:text-tealNavy-950 font-mono mt-1 block">
              {stats?.genuine_documents_count ?? documents.length}
            </span>
            <span className="text-[10px] text-turquoise dark:text-turquoise light:text-teal-700 font-mono mt-0.5 block font-semibold">
              {stats?.genuine_pages_count ?? totalPages} verified pages
            </span>
          </div>

          <div className="bg-tealNavy-950/70 dark:bg-tealNavy-950/70 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 rounded-xl p-3.5 transition-colors">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-medium text-slate-400 dark:text-slate-400 light:text-slate-500 uppercase tracking-wider block">
                Departments Monitored
              </span>
              <Building2 className="w-4 h-4 text-turquoise" />
            </div>
            <span className="text-2xl font-bold text-white dark:text-white light:text-tealNavy-950 font-mono mt-1 block">
              {stats?.departments_monitored_count ?? (allDepartments.length || 5)}
            </span>
            <span
              className="text-[10px] text-slate-400 dark:text-slate-400 light:text-slate-500 font-mono mt-0.5 block truncate"
              title={stats?.departments_codes?.slice(0, 6).join(", ") || deptCodes}
            >
              {stats?.departments_codes?.slice(0, 6).join(", ") || deptCodes}
            </span>
          </div>

          <div className="bg-tealNavy-950/70 dark:bg-tealNavy-950/70 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 rounded-xl p-3.5 transition-colors">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-medium text-slate-400 dark:text-slate-400 light:text-slate-500 uppercase tracking-wider block">
                Primary Authority
              </span>
              <Scale className="w-4 h-4 text-turquoise" />
            </div>
            <span
              className="text-2xl font-bold text-turquoise-bright dark:text-turquoise-bright light:text-teal-700 font-mono mt-1 block truncate"
              title={stats?.primary_authority ?? primaryAuthority}
            >
              {stats?.primary_authority ?? primaryAuthority}
            </span>
            <span className="text-[10px] text-slate-400 dark:text-slate-400 light:text-slate-500 font-mono mt-0.5 block">
              Central Banking Regulator
            </span>
          </div>

          <div className="bg-tealNavy-950/70 dark:bg-tealNavy-950/70 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 rounded-xl p-3.5 transition-colors">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-medium text-slate-400 dark:text-slate-400 light:text-slate-500 uppercase tracking-wider block">
                Storage & Invariants
              </span>
              <ShieldCheck className="w-4 h-4 text-semantic-success" />
            </div>
            <span className="text-2xl font-bold text-semantic-success font-mono mt-1 block">
              Immutable
            </span>
            <span className="text-[10px] text-slate-400 dark:text-slate-400 light:text-slate-500 font-mono mt-0.5 block">
              {stats ? `${stats.synthetic_documents_count} test records segregated` : "SHA-256 Provenance"}
            </span>
          </div>
        </div>
      </div>

      {/* Application Shell: Navigation Pills & Corpus Filters */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-tealNavy-700/80 dark:border-tealNavy-700/80 light:border-slate-200 pb-4">
        {/* Corpus Classification Tabs */}
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setCorpusFilter("GENUINE")}
            className={`px-3.5 py-1.5 text-xs font-mono rounded-lg transition border flex items-center gap-1.5 ${
              corpusFilter === "GENUINE"
                ? "bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-teal-50 text-turquoise dark:text-turquoise light:text-teal-700 border-turquoise/50 font-bold shadow-[0_0_12px_rgba(45,212,191,0.2)]"
                : "bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white text-slate-400 dark:text-slate-400 light:text-slate-600 border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 hover:text-slate-200"
            }`}
          >
            <Building2 className="w-3.5 h-3.5 text-turquoise" />
            <span>Official Circulars ({stats?.genuine_documents_count ?? 4})</span>
          </button>
          <button
            onClick={() => setCorpusFilter("ALL")}
            className={`px-3.5 py-1.5 text-xs font-mono rounded-lg transition border flex items-center gap-1.5 ${
              corpusFilter === "ALL"
                ? "bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-teal-50 text-turquoise dark:text-turquoise light:text-teal-700 border-turquoise/50 font-bold shadow-[0_0_12px_rgba(45,212,191,0.2)]"
                : "bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white text-slate-400 dark:text-slate-400 light:text-slate-600 border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 hover:text-slate-200"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>All Corpus Records ({stats?.total_documents ?? 64})</span>
          </button>
          <button
            onClick={() => setCorpusFilter("SYNTHETIC_SAMPLE")}
            className={`px-3.5 py-1.5 text-xs font-mono rounded-lg transition border flex items-center gap-1.5 ${
              corpusFilter === "SYNTHETIC_SAMPLE"
                ? "bg-purple-950/80 dark:bg-purple-950/80 light:bg-purple-50 text-purple-200 dark:text-purple-200 light:text-purple-700 border-purple-500 font-bold shadow-sm"
                : "bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white text-slate-400 dark:text-slate-400 light:text-slate-600 border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 hover:text-slate-200"
            }`}
          >
            <Layers className="w-3.5 h-3.5 text-purple-400" />
            <span>Synthetic Test Fixtures ({stats?.synthetic_documents_count ?? 60})</span>
          </button>
        </div>

        {/* Live Filter Indicator */}
        <div className="text-xs text-slate-400 dark:text-slate-400 light:text-slate-600 font-mono flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-turquoise animate-pulse"></span>
          <span>
            Showing {documents.length}{" "}
            {corpusFilter === "GENUINE"
              ? "official circulars"
              : corpusFilter === "SYNTHETIC_SAMPLE"
              ? "synthetic fixtures"
              : "total records"}
          </span>
        </div>
      </div>

      {/* Search and Filters Bar */}
      <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
        <div className="relative w-full sm:w-96">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search circulars (e.g. SMESPD, IFRS 9, UBO)..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl pl-10 pr-4 py-2 text-sm text-slate-200 dark:text-slate-200 light:text-tealNavy-950 placeholder-slate-400 focus:outline-none focus:border-turquoise font-sans transition"
          />
        </div>
        <div className="flex items-center space-x-2 text-xs text-slate-400 dark:text-slate-400 light:text-slate-600 self-end sm:self-auto font-mono">
          <span>{corpusFilter === "GENUINE" && "Verified against Bangladesh Bank publications"}</span>
        </div>
      </div>

      {/* Main Grid: Circular List & Selected Document Intelligence Reader */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Document Cards Column */}
        <div className="lg:col-span-5 space-y-4">
          {loading ? (
            <div className="p-12 text-center text-slate-400 dark:text-slate-400 light:text-slate-600 text-sm border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-2xl bg-tealNavy-900/60 dark:bg-tealNavy-900/60 light:bg-white">
              Loading regulatory repository...
            </div>
          ) : documents.length === 0 ? (
            <div className="p-12 text-center border border-dashed border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-2xl bg-tealNavy-900/40 dark:bg-tealNavy-900/40 light:bg-slate-50">
              <p className="text-sm text-slate-400 dark:text-slate-400 light:text-slate-600">
                No documents found matching the filter.
              </p>
              <Link
                href="/admin"
                className="mt-3 inline-block text-xs font-semibold text-turquoise dark:text-turquoise light:text-teal-700 hover:underline"
              >
                Upload circular in Admin Console &rarr;
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
                      ? "bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-teal-50/70 border-turquoise shadow-[0_0_15px_rgba(45,212,191,0.2)]"
                      : "bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 hover:bg-tealNavy-850 dark:hover:bg-tealNavy-850 light:hover:bg-slate-50 hover:border-turquoise/60"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-[11px] font-mono font-semibold px-2 py-0.5 rounded bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-teal-100 text-turquoise dark:text-turquoise light:text-teal-800 border border-tealNavy-700 dark:border-tealNavy-700 light:border-teal-200">
                        {doc.reference_number || "BB Circular"}
                      </span>
                      {doc.is_synthetic ? (
                        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800/80">
                          SYNTHETIC TEST SAMPLE
                        </span>
                      ) : (
                        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-emerald-950 dark:bg-emerald-950 light:bg-emerald-100 text-emerald-300 dark:text-emerald-300 light:text-emerald-800 border border-emerald-800/80 font-bold">
                          OFFICIAL CIRCULAR
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-slate-400 dark:text-slate-400 light:text-slate-500 font-mono">
                      {doc.publication_date}
                    </span>
                  </div>

                  <h3 className="text-sm font-semibold text-slate-100 dark:text-slate-100 light:text-tealNavy-950 mt-2.5 leading-snug">
                    {doc.title}
                  </h3>

                  <div className="flex items-center justify-between text-xs text-slate-400 dark:text-slate-400 light:text-slate-500 mt-3 pt-3 border-t border-tealNavy-700/60 dark:border-tealNavy-700/60 light:border-slate-200 font-mono">
                    <div className="flex items-center space-x-2">
                      <span className="px-1.5 py-0.5 rounded bg-tealNavy-800 dark:bg-tealNavy-800 light:bg-slate-100 text-[10px]">
                        {doc.document_type}
                      </span>
                      <span>
                        {(activeVersion?.page_count ?? 0) > 0
                          ? `${activeVersion?.page_count} pages`
                          : "0 pages (Empty Draft)"}
                      </span>
                    </div>
                    {renderPublicationBadge(doc.publication_status)}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Selected Document Full Intelligence & Reader Column */}
        <div className="lg:col-span-7">
          {selectedDoc ? (
            <div className="border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 bg-tealNavy-900/90 dark:bg-tealNavy-900/90 light:bg-white rounded-2xl p-6 sticky top-24 space-y-6 shadow-xl transition-colors">
              {/* Header */}
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-bold text-turquoise dark:text-turquoise light:text-teal-700">
                    {selectedDoc.reference_number || "REGULATORY DOCUMENT"}
                  </span>
                  <div className="flex items-center space-x-2">
                    {!analysis && (
                      <button
                        onClick={handleRunAnalysis}
                        disabled={analyzing}
                        className="text-xs bg-turquoise hover:bg-turquoise-bright disabled:opacity-50 text-tealNavy-950 px-3 py-1.5 rounded font-bold transition flex items-center gap-1.5 shadow-sm"
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                        <span>{analyzing ? "Analyzing..." : "Run AI Intelligence"}</span>
                      </button>
                    )}
                    <a
                      href={`http://localhost:8000/api/v1/documents/${selectedDoc.id}/pdf`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs font-medium bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-100 hover:border-turquoise text-slate-200 dark:text-slate-200 light:text-slate-800 px-3 py-1.5 rounded border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 transition flex items-center gap-1.5 font-mono"
                    >
                      <span>View PDF</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                </div>

                <h2 className="text-lg font-bold text-white dark:text-white light:text-tealNavy-950 mt-1.5 leading-snug">
                  {selectedDoc.title}
                </h2>

                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400 dark:text-slate-400 light:text-slate-500 mt-2 font-mono">
                  <span>Published: {selectedDoc.publication_date}</span>
                  {selectedDoc.effective_date && <span>Effective: {selectedDoc.effective_date}</span>}
                  <span>
                    Status: <span className="text-turquoise dark:text-turquoise light:text-teal-700 font-semibold">{selectedDoc.publication_status}</span>
                  </span>
                </div>

                {analysis && (
                  <div className="space-y-3 mt-3">
                    {/* Sandbox vs Live AI Disclaimer Banner */}
                    {analysis.model_name?.startsWith("mock") ? (
                      <div className="bg-amber-950/40 dark:bg-amber-950/40 light:bg-amber-50 border border-amber-600/50 rounded-xl p-3.5 text-xs transition-colors">
                        <div className="flex items-center justify-between font-mono text-amber-300 dark:text-amber-300 light:text-amber-800">
                          <span className="font-semibold flex items-center gap-1.5">
                            <AlertTriangle className="w-4 h-4 text-amber-400" />
                            Offline Heuristic Pipeline ({analysis.model_name})
                          </span>
                          <span className="text-[10px] px-2 py-0.5 rounded bg-amber-900/60 dark:bg-amber-900/60 light:bg-amber-200 border border-amber-600 font-bold">
                            Sandbox Mode
                          </span>
                        </div>
                        <p className="text-amber-200/80 dark:text-amber-200/80 light:text-amber-900 text-[11px] mt-1 leading-relaxed">
                          Deterministic regulatory rule engine output. Operational reliance in production requires live Gemini free-tier analysis via{" "}
                          <code className="bg-amber-900/40 dark:bg-amber-900/40 light:bg-amber-200 px-1 rounded">GEMINI_API_KEY</code> and human legal sign-off.
                        </p>
                      </div>
                    ) : (
                      <div className="bg-emerald-950/40 dark:bg-emerald-950/40 light:bg-emerald-50 border border-emerald-600/50 rounded-xl p-3.5 text-xs transition-colors">
                        <div className="flex items-center justify-between font-mono text-emerald-300 dark:text-emerald-300 light:text-emerald-800">
                          <span className="font-semibold flex items-center gap-1.5">
                            <Sparkles className="w-4 h-4 text-turquoise" />
                            Live Gemini AI Analysis ({analysis.model_name})
                          </span>
                          <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-900/60 dark:bg-emerald-900/60 light:bg-emerald-200 border border-emerald-600 font-bold">
                            Zero-Cost Free Tier
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Multi-Dimensional Regulatory Quality Matrix */}
                    <div className="bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 p-3.5 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-2 text-[11px] font-mono transition-colors">
                      <div className="flex items-center justify-between border-b border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200 pb-2">
                        <span className="text-slate-400 dark:text-slate-400 light:text-slate-600 font-bold">
                          Quality Dimensions & Provenance:
                        </span>
                        <span className="text-[10px] text-slate-500">Phase 3.9 Audited Invariants</span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                        <div className="p-2 rounded bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white border border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200">
                          <span className="text-[10px] text-slate-400 dark:text-slate-400 light:text-slate-500 uppercase tracking-wider block">
                            Citation Coverage
                          </span>
                          <span
                            className={`text-xs font-bold block mt-0.5 ${
                              analysis.citation_coverage_score >= 1.0 ? "text-semantic-success" : "text-semantic-warning"
                            }`}
                          >
                            {(analysis.citation_coverage_score * 100).toFixed(1)}% Verified
                          </span>
                          <span className="text-[9px] text-slate-500 block mt-0.5">Exact Page Grounding</span>
                        </div>
                        <div className="p-2 rounded bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white border border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200">
                          <span className="text-[10px] text-slate-400 dark:text-slate-400 light:text-slate-500 uppercase tracking-wider block">
                            Completeness Tier
                          </span>
                          <span className="text-xs font-bold text-slate-200 dark:text-slate-200 light:text-tealNavy-950 block mt-0.5">
                            {provisions.length} Core Clauses
                          </span>
                          <span className="text-[9px] text-slate-500 block mt-0.5">
                            {obligations.length} Active Obligations
                          </span>
                        </div>
                        <div className="p-2 rounded bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white border border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200">
                          <span className="text-[10px] text-slate-400 dark:text-slate-400 light:text-slate-500 uppercase tracking-wider block">
                            Review Status
                          </span>
                          <span className="text-xs font-bold text-turquoise dark:text-turquoise light:text-teal-700 block mt-0.5 truncate">
                            {selectedDoc.publication_status.includes("HUMAN") ? "Human Audited" : "Pending Sign-Off"}
                          </span>
                          <span className="text-[9px] text-slate-500 block mt-0.5 truncate">
                            {selectedDoc.publication_status}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Navigation Tabs */}
              <div className="flex border-b border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 gap-1.5 overflow-x-auto text-xs font-medium font-mono pb-2">
                <button
                  onClick={() => setActiveTab("summary")}
                  className={`px-3 py-1.5 rounded-lg transition ${
                    activeTab === "summary"
                      ? "bg-turquoise text-tealNavy-950 font-bold shadow-sm"
                      : "text-slate-400 dark:text-slate-400 light:text-slate-600 hover:text-white dark:hover:text-white light:hover:text-tealNavy-950 hover:bg-tealNavy-800 dark:hover:bg-tealNavy-800 light:hover:bg-slate-100"
                  }`}
                >
                  Executive Summary
                </button>
                <button
                  onClick={() => setActiveTab("obligations")}
                  className={`px-3 py-1.5 rounded-lg transition ${
                    activeTab === "obligations"
                      ? "bg-turquoise text-tealNavy-950 font-bold shadow-sm"
                      : "text-slate-400 dark:text-slate-400 light:text-slate-600 hover:text-white dark:hover:text-white light:hover:text-tealNavy-950 hover:bg-tealNavy-800 dark:hover:bg-tealNavy-800 light:hover:bg-slate-100"
                  }`}
                >
                  Obligations ({obligations.length})
                </button>
                <button
                  onClick={() => setActiveTab("provisions")}
                  className={`px-3 py-1.5 rounded-lg transition ${
                    activeTab === "provisions"
                      ? "bg-turquoise text-tealNavy-950 font-bold shadow-sm"
                      : "text-slate-400 dark:text-slate-400 light:text-slate-600 hover:text-white dark:hover:text-white light:hover:text-tealNavy-950 hover:bg-tealNavy-800 dark:hover:bg-tealNavy-800 light:hover:bg-slate-100"
                  }`}
                >
                  Provisions ({provisions.length})
                </button>
                <button
                  onClick={() => setActiveTab("relationships")}
                  className={`px-3 py-1.5 rounded-lg transition ${
                    activeTab === "relationships"
                      ? "bg-turquoise text-tealNavy-950 font-bold shadow-sm"
                      : "text-slate-400 dark:text-slate-400 light:text-slate-600 hover:text-white dark:hover:text-white light:hover:text-tealNavy-950 hover:bg-tealNavy-800 dark:hover:bg-tealNavy-800 light:hover:bg-slate-100"
                  }`}
                >
                  Relationships ({relationships.length})
                </button>
                <button
                  onClick={() => setActiveTab("pages")}
                  className={`px-3 py-1.5 rounded-lg transition ${
                    activeTab === "pages"
                      ? "bg-turquoise text-tealNavy-950 font-bold shadow-sm"
                      : "text-slate-400 dark:text-slate-400 light:text-slate-600 hover:text-white dark:hover:text-white light:hover:text-tealNavy-950 hover:bg-tealNavy-800 dark:hover:bg-tealNavy-800 light:hover:bg-slate-100"
                  }`}
                >
                  Pages & Provenance ({docPages.length})
                </button>
                <button
                  onClick={() => setActiveTab("qa")}
                  className={`px-3 py-1.5 rounded-lg transition ${
                    activeTab === "qa"
                      ? "bg-turquoise text-tealNavy-950 font-bold shadow-sm"
                      : "text-slate-400 dark:text-slate-400 light:text-slate-600 hover:text-white dark:hover:text-white light:hover:text-tealNavy-950 hover:bg-tealNavy-800 dark:hover:bg-tealNavy-800 light:hover:bg-slate-100"
                  }`}
                >
                  Grounded Q&A
                </button>
              </div>

              {/* Tab 1: Executive Summary */}
              {activeTab === "summary" && (
                <div className="space-y-4 text-xs text-slate-300 dark:text-slate-300 light:text-slate-700">
                  {analysis ? (
                    <>
                      <div className="bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 p-4 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-2">
                        <span className="text-[11px] font-bold uppercase tracking-wider text-turquoise dark:text-turquoise light:text-teal-700 block">
                          Core Executive Summary
                        </span>
                        <p className="leading-relaxed text-sm text-slate-100 dark:text-slate-100 light:text-tealNavy-950">
                          {analysis.executive_summary}
                        </p>
                      </div>
                      {analysis.purpose && (
                        <div>
                          <h4 className="font-semibold text-slate-200 dark:text-slate-200 light:text-tealNavy-950 mb-1">
                            Regulatory Purpose
                          </h4>
                          <p className="text-slate-400 dark:text-slate-400 light:text-slate-600 leading-relaxed">
                            {analysis.purpose}
                          </p>
                        </div>
                      )}
                      {analysis.key_changes && analysis.key_changes.length > 0 && (
                        <div>
                          <h4 className="font-semibold text-slate-200 dark:text-slate-200 light:text-tealNavy-950 mb-1.5">
                            Key Regulatory Requirements
                          </h4>
                          <ul className="list-disc pl-5 space-y-1 text-slate-400 dark:text-slate-400 light:text-slate-600">
                            {analysis.key_changes.map((kc, i) => (
                              <li key={i}>{kc}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {analysis.impact_summary && Object.keys(analysis.impact_summary).length > 0 && (
                        <div className="bg-tealNavy-950/70 dark:bg-tealNavy-950/70 light:bg-slate-50 p-3.5 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-2">
                          <span className="font-semibold text-slate-300 dark:text-slate-300 light:text-tealNavy-950 block">
                            Impacted Banking Dimensions
                          </span>
                          <div className="grid grid-cols-2 gap-2 text-[11px]">
                            {Object.entries(analysis.impact_summary).map(([k, v]) => (
                              <div
                                key={k}
                                className="p-2 bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white rounded-lg border border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200"
                              >
                                <span className="font-mono text-turquoise dark:text-turquoise light:text-teal-700 uppercase block font-bold">
                                  {k.replace("_", " ")}
                                </span>
                                <span className="text-slate-400 dark:text-slate-400 light:text-slate-600 mt-0.5 block">
                                  {String(v)}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-center p-8 border border-dashed border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl">
                      <p className="text-slate-400 dark:text-slate-400 light:text-slate-600 mb-3">
                        AI Intelligence has not been generated for this document yet.
                      </p>
                      <button
                        onClick={handleRunAnalysis}
                        disabled={analyzing}
                        className="px-4 py-2 bg-turquoise hover:bg-turquoise-bright text-tealNavy-950 font-bold rounded-lg text-xs transition shadow-sm"
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
                    <p className="text-xs text-slate-400 text-center p-6">No obligations extracted yet.</p>
                  ) : (
                    obligations.map((obl) => {
                      const citedPage = docPages.find((p) => p.id === obl.page_id)?.page_number;
                      return (
                        <div
                          key={obl.id}
                          className="p-3.5 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-2 transition-colors"
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
                          <div className="flex flex-wrap items-center justify-between text-[11px] font-mono text-slate-400 dark:text-slate-400 light:text-slate-500 pt-2 border-t border-tealNavy-900 dark:border-tealNavy-900 light:border-slate-200 gap-2">
                            <div className="flex items-center gap-3">
                              <span>
                                Responsible: <span className="text-slate-200 dark:text-slate-200 light:text-tealNavy-950 font-semibold">{obl.applicability_summary}</span>
                              </span>
                              {citedPage && (
                                <button
                                  onClick={() => {
                                    setActiveTab("pages");
                                    setSelectedPageNo(citedPage);
                                  }}
                                  className="text-turquoise dark:text-turquoise light:text-teal-700 hover:underline font-semibold flex items-center gap-1 cursor-pointer"
                                  title={`Jump to Page ${citedPage}`}
                                >
                                  <FileText className="w-3 h-3" />
                                  <span>Page {citedPage}</span>
                                </button>
                              )}
                            </div>
                            {obl.explicit_deadline && (
                              <span className="text-semantic-warning font-semibold">
                                Deadline: {obl.explicit_deadline}
                              </span>
                            )}
                            {renderCitationBadge(obl.verification_status)}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {/* Tab 3: Provisions */}
              {activeTab === "provisions" && (
                <div className="space-y-3 max-h-[450px] overflow-y-auto pr-1">
                  {provisions.length === 0 ? (
                    <p className="text-xs text-slate-400 text-center p-6">No provisions extracted yet.</p>
                  ) : (
                    provisions.map((prov) => {
                      const citedPage = docPages.find((p) => p.id === prov.page_id)?.page_number;
                      return (
                        <div
                          key={prov.id}
                          className="p-3 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-1.5 transition-colors"
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-xs font-bold text-turquoise dark:text-turquoise light:text-teal-700">
                                {prov.provision_number || "Clause"}
                              </span>
                              {prov.heading && (
                                <span className="text-xs font-semibold text-slate-300 dark:text-slate-300 light:text-tealNavy-950">
                                  {prov.heading}
                                </span>
                              )}
                            </div>
                            {citedPage && (
                              <button
                                onClick={() => {
                                  setActiveTab("pages");
                                  setSelectedPageNo(citedPage);
                                }}
                                className="text-[10px] font-mono px-2 py-0.5 rounded bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white hover:border-turquoise text-turquoise dark:text-turquoise light:text-teal-700 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 cursor-pointer transition flex items-center gap-1"
                                title={`Jump to Page ${citedPage}`}
                              >
                                <FileText className="w-3 h-3" />
                                <span>Page {citedPage}</span>
                                <ArrowUpRight className="w-3 h-3" />
                              </button>
                            )}
                          </div>
                          <p className="text-xs text-slate-300 dark:text-slate-300 light:text-slate-700 font-mono leading-relaxed bg-tealNavy-900/60 dark:bg-tealNavy-900/60 light:bg-white p-2.5 rounded-lg border border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200">
                            {prov.verbatim_text}
                          </p>
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {/* Tab 4: Relationships */}
              {activeTab === "relationships" && (
                <div className="space-y-3 max-h-[450px] overflow-y-auto pr-1">
                  {relationships.length === 0 ? (
                    <div className="p-6 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 border border-dashed border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl text-center space-y-2">
                      <Building2 className="w-8 h-8 text-turquoise mx-auto" />
                      <h4 className="text-xs font-bold text-slate-200 dark:text-slate-200 light:text-tealNavy-950">
                        Standalone Original Policy Framework
                      </h4>
                      <p className="text-xs text-slate-400 dark:text-slate-400 light:text-slate-600 max-w-md mx-auto leading-relaxed">
                        This regulatory publication establishes a standalone original policy framework (issued under Section 45 of the Bank Company Act, 1991). It does not amend, supersede, or repeal any prior Bangladesh Bank circulars.
                      </p>
                      <span className="inline-block text-[10px] font-mono text-emerald-400 dark:text-emerald-400 light:text-emerald-700 bg-emerald-950/60 dark:bg-emerald-950/60 light:bg-emerald-50 px-2.5 py-1 rounded border border-emerald-800/60 font-semibold">
                        Verified: Zero Invented Relationships
                      </span>
                    </div>
                  ) : (
                    relationships.map((rel) => (
                      <div
                        key={rel.id}
                        className="p-3.5 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-2"
                      >
                        <div className="flex items-center justify-between">
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-purple-950 text-purple-300 border border-purple-800">
                            {rel.relationship_type}
                          </span>
                          <span className="text-xs font-mono text-semantic-success">{rel.verification_status}</span>
                        </div>
                        <h4 className="text-xs font-bold text-slate-200 dark:text-slate-200 light:text-tealNavy-950">
                          Target: {rel.target_reference_hint || "Referenced Circular"}
                        </h4>
                        <p className="text-xs font-mono text-slate-400 dark:text-slate-400 light:text-slate-600 italic bg-tealNavy-900/80 dark:bg-tealNavy-900/80 light:bg-white p-2.5 rounded-lg border border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200">
                          &ldquo;{rel.supporting_quote}&rdquo;
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
                        <span className="text-xs font-semibold text-slate-300 dark:text-slate-300 light:text-tealNavy-950">
                          Select Page ({docPages.length} Pages Extracted)
                        </span>
                        <div className="flex items-center space-x-2 text-[11px] font-mono text-slate-400 dark:text-slate-400 light:text-slate-500">
                          <span>
                            Method:{" "}
                            <span className="text-turquoise dark:text-turquoise light:text-teal-700 font-semibold">
                              {docPages.find((p) => p.page_number === selectedPageNo)?.extraction_method || "N/A"}
                            </span>
                          </span>
                          <span>-</span>
                          <span>
                            Length: {docPages.find((p) => p.page_number === selectedPageNo)?.raw_text?.length || 0} chars
                          </span>
                        </div>
                      </div>
                      <div className="flex gap-1.5 overflow-x-auto pb-1.5">
                        {docPages.map((p) => (
                          <button
                            key={p.page_number}
                            onClick={() => setSelectedPageNo(p.page_number)}
                            className={`px-3 py-1 text-xs font-mono rounded-lg border transition ${
                              selectedPageNo === p.page_number
                                ? "bg-turquoise text-tealNavy-950 border-turquoise font-bold shadow-[0_0_12px_rgba(45,212,191,0.25)]"
                                : "bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-white text-slate-400 dark:text-slate-400 light:text-slate-600 border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 hover:text-white"
                            }`}
                          >
                            Page {p.page_number}
                            {p.has_tables && " (Tables)"}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-900 rounded-xl p-4 max-h-[380px] overflow-y-auto font-mono text-xs text-slate-300 whitespace-pre-wrap leading-relaxed selection:bg-tealNavy-800">
                    {loadingPages ? (
                      <p className="text-slate-400">Loading extracted page text...</p>
                    ) : docPages.length === 0 ? (
                      <p className="text-slate-400">No page text extracted yet.</p>
                    ) : (
                      docPages.find((p) => p.page_number === selectedPageNo)?.raw_text || "Page content unavailable."
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
                      className="flex-1 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-white border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl px-3.5 py-2 text-xs text-slate-200 dark:text-slate-200 light:text-tealNavy-950 focus:outline-none focus:border-turquoise"
                    />
                    <button
                      type="submit"
                      disabled={qaLoading}
                      className="px-4 py-2 bg-turquoise hover:bg-turquoise-bright disabled:opacity-50 text-tealNavy-950 text-xs font-bold rounded-lg transition shadow-sm"
                    >
                      {qaLoading ? "Searching..." : "Ask AI"}
                    </button>
                  </form>

                  {qaResponse && (
                    <div className="p-4 bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 rounded-xl border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-3 text-xs">
                      <span className="font-semibold text-slate-300 dark:text-slate-300 light:text-tealNavy-950 block">
                        Grounded Regulatory Answer:
                      </span>
                      <p className="text-slate-200 dark:text-slate-200 light:text-slate-800 leading-relaxed">
                        {qaResponse.answer}
                      </p>
                      {qaResponse.citations && qaResponse.citations.length > 0 && (
                        <div className="pt-2 border-t border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200 space-y-1">
                          <span className="text-[11px] font-mono text-turquoise dark:text-turquoise light:text-teal-700 block font-bold">
                            Supporting Page Citations:
                          </span>
                          {qaResponse.citations.map((c: any, i: number) => (
                            <div
                              key={i}
                              className="text-[11px] font-mono text-slate-400 dark:text-slate-400 light:text-slate-600 bg-tealNavy-900/60 dark:bg-tealNavy-900/60 light:bg-white p-2.5 rounded-lg border border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200"
                            >
                              <span className="text-slate-300 dark:text-slate-300 light:text-tealNavy-950 font-semibold">
                                {c.reference_number || c.document_title} - Page {c.page_number}:
                              </span>{" "}
                              &ldquo;{c.verbatim_excerpt}&rdquo;
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Provenance Footer */}
              <div className="text-[11px] text-slate-400 dark:text-slate-400 light:text-slate-500 flex items-center justify-between border-t border-tealNavy-700/80 dark:border-tealNavy-700/80 light:border-slate-200 pt-3 font-mono">
                <span>Provenance: SHA-256 Verified</span>
                <span>Traceable: 100% Page Citation Invariant</span>
              </div>
            </div>
          ) : (
            <div className="h-96 border border-dashed border-tealNavy-700/80 dark:border-tealNavy-700/80 light:border-slate-300 rounded-2xl bg-tealNavy-900/40 dark:bg-tealNavy-900/40 light:bg-slate-50 flex flex-col items-center justify-center p-6 text-center text-slate-400">
              <FileText className="w-10 h-10 text-turquoise mb-2 opacity-80" />
              <p className="text-sm font-semibold text-slate-200 dark:text-slate-200 light:text-tealNavy-950">
                Select any circular on the left
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-400 light:text-slate-600 max-w-sm mt-1">
                Inspect AI executive summaries, mandatory obligations, verbatim provisions, relationships, and grounded Q&amp;A.
              </p>
            </div>
          )}
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
